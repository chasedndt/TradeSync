import asyncio
import json
import os
import httpx
from .redis_client import redis_client
from tradesync_core import normalize_symbol
from tradesync_core import EnhancedScorer

STREAM_NAME = "x:signals.funding"
MARKET_DATA_URL = os.getenv("MARKET_DATA_URL", "http://market-data:8005")
GROUP_NAME = "fusion-engine"
LEGACY_GROUP_NAME = "opportunity-builder"  # For migration
CONSUMER_NAME = os.getenv("HOSTNAME", "fusion-engine-1")

# Config from env
OPPORTUNITY_THRESHOLD = float(os.getenv("OPPORTUNITY_THRESHOLD", "2.0"))
OPPORTUNITY_TTL_SECONDS = int(os.getenv("OPPORTUNITY_TTL_SECONDS", "900"))
CLAIM_IDLE_MS = int(os.getenv("CLAIM_IDLE_MS", "60000"))
CLAIM_BATCH = int(os.getenv("CLAIM_BATCH", "50"))
STREAM_READ_COUNT = int(os.getenv("STREAM_READ_COUNT", "50"))
STREAM_BLOCK_MS = int(os.getenv("STREAM_BLOCK_MS", "5000"))

# Shared stats (will be updated by worker, read by main.py)
stats = {"opps_created": 0}

# Phase 3C: Enhanced scorer instance
enhanced_scorer = EnhancedScorer()

async def fetch_market_snapshot(symbol: str, venue: str = "hyperliquid"):
    """Fetch current market snapshot for microstructure data."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{MARKET_DATA_URL}/snapshot/{venue}/{symbol}",
                timeout=2.0
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        print(f"[Worker] Failed to fetch market snapshot: {e}")
    return None

async def process_message(msg_id, data):
    from .db import db
    raw_payload = data.get("data")
    if not raw_payload:
        await redis_client.client.xack(STREAM_NAME, GROUP_NAME, msg_id)
        return

    try:
        payload = json.loads(raw_payload)
        score = float(payload.get("score", 0))
        symbol = normalize_symbol(payload.get("symbol", "unknown"))
        signal_id = payload.get("id")
        event_ids = payload.get("event_ids", [])
        
        # 1. Actionability: Threshold check
        if abs(score) < OPPORTUNITY_THRESHOLD:
            await redis_client.client.xack(STREAM_NAME, GROUP_NAME, msg_id)
            return

        # 2. Actionability: Require event_ids (for traceability)
        if not event_ids:
            print(f"[Worker] Skipping signal {signal_id} for {symbol}: No event_ids")
            await redis_client.client.xack(STREAM_NAME, GROUP_NAME, msg_id)
            return

        # Phase 3C: Fetch market snapshot for microstructure data
        market_snapshot = await fetch_market_snapshot(symbol)
        microstructure = market_snapshot.get("microstructure") if market_snapshot else None
        regime_data = market_snapshot.get("regimes") if market_snapshot else None

        # Phase 3C: Compute enhanced score with breakdown
        confidence = payload.get("confidence", 0.5)
        enhanced_score = enhanced_scorer.compute_enhanced_score(
            raw_score=score,
            signal_confidence=confidence,
            symbol=symbol,
            microstructure=microstructure,
            regime_data=regime_data,
            exposure_data=None  # TODO: Fetch from state-api when available
        )

        # Phase 3C: Use final_score from enhanced scoring
        final_score = enhanced_score.score_breakdown.final_score

        # 3. Create Opportunity Record with enhanced confluence data
        opp_data = {
            "symbol": symbol,
            "timeframe": payload.get("timeframe", "1m"),
            "bias": final_score,  # Use enhanced score
            "quality": confidence * 100,
            "dir": payload.get("direction", "NEUTRAL"),
            "links": {
                "signal_id": signal_id,
                "event_ids": event_ids
            },
            "signal_id": signal_id,
            "ttl_seconds": OPPORTUNITY_TTL_SECONDS,
            # Phase 3C: Include enhanced scoring data in confluence
            "confluence": enhanced_score.to_dict()
        }

        # 4. Idempotent Insert (Strict ACK-after-commit)
        # UNIQUE(signal_id) in DB ensures we don't double-create.
        new_id = await db.insert_opportunity(opp_data)
        if new_id:
            print(f"[Worker] Created Opportunity {new_id} for signal {signal_id}. ACK after DB commit.")
            stats["opps_created"] += 1
        else:
            print(f"[Worker] Duplicate or existing signal {signal_id}, skipping. ACK after confirmed idempotent.")

        # 5. XACK only after successful processing
        await redis_client.client.xack(STREAM_NAME, GROUP_NAME, msg_id)

    except (json.JSONDecodeError, ValueError) as e:
        print(f"[Worker] Error parsing msg {msg_id}: {e}")
        await redis_client.client.xack(STREAM_NAME, GROUP_NAME, msg_id)

async def recover_pending():
    print(f"[Worker] Starting recovery for {STREAM_NAME}:{GROUP_NAME}")
    while True:
        messages = await redis_client.claim_stale_pending(
            STREAM_NAME, GROUP_NAME, CONSUMER_NAME, CLAIM_IDLE_MS, CLAIM_BATCH
        )
        if not messages:
            print("[Worker] No more stale pending messages.")
            break
        
        count = sum(len(entries) for _, entries in messages)
        print(f"[Worker] Recovered {count} pending messages via XCLAIM")
        
        for stream, entries in messages:
            for msg_id, data in entries:
                await process_message(msg_id, data)

async def run_worker():
    print(f"Starting worker: stream={STREAM_NAME}, group={GROUP_NAME}, consumer={CONSUMER_NAME}")
    print(f"Threshold: {OPPORTUNITY_THRESHOLD}, TTL: {OPPORTUNITY_TTL_SECONDS}")
    
    # 1. Recover pending messages first
    try:
        await recover_pending()
    except Exception as e:
        print(f"[Worker] Recovery failed: {e}")
    
    # 2. Main consumer loop
    while True:
        try:
            messages = await redis_client.client.xreadgroup(
                GROUP_NAME, 
                CONSUMER_NAME, 
                {STREAM_NAME: ">"}, 
                count=STREAM_READ_COUNT, 
                block=STREAM_BLOCK_MS
            )
            
            if not messages:
                continue
                
            for stream, entries in messages:
                for msg_id, data in entries:
                    await process_message(msg_id, data)
                    
        except asyncio.CancelledError:
            print("Worker stopping...")
            break
        except Exception as e:
            print(f"Worker Error: {e}")
            await asyncio.sleep(5)  # Backoff on error
