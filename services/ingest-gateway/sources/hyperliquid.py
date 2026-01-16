import asyncio
import httpx
import uuid
import json
from datetime import datetime
from typing import List, Optional
from app.models import NormalizedEvent
from app.db import insert_event

# Configuration
HYPERLIQUID_API_URL = "https://api.hyperliquid.xyz/info"
TARGET_MARKETS = ["BTC", "ETH", "SOL"]

async def poll_hyperliquid_markets():
    """
    Background task to poll Hyperliquid markets and ingest snapshots.
    """
    print("Starting Hyperliquid Poller...")
    while True:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    HYPERLIQUID_API_URL, 
                    json={"type": "metaAndAssetCtxs"},
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()

            # data is [meta, assetCtxs]
            # meta['universe'] has the list of assets
            # assetCtxs is a list of contexts corresponding to universe
            
            universe = data[0]['universe']
            asset_ctxs = data[1]
            
            ts = datetime.now()
            
            for i, asset_info in enumerate(universe):
                symbol = asset_info['name']
                
                if symbol not in TARGET_MARKETS:
                    continue
                
                ctx = asset_ctxs[i]
                
                # Build payload
                payload = {
                    "mark": ctx.get("markPx"),
                    "funding": ctx.get("funding"),
                    "oi": ctx.get("openInterest"),
                    "volume": ctx.get("dayNtlVlm"),
                    "oracle": ctx.get("oraclePx"),
                    "venue": "hyperliquid"
                }
                
                event_id = str(uuid.uuid4())
                event_hash = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"hyperliquid:{symbol}:{ts.isoformat()}"))
                
                provenance = {
                    "poller": "hyperliquid_poller",
                    "venue": "hyperliquid",
                    "polled_at": ts.isoformat()
                }
                
                # Canonical Symbol: BTC -> BTC-PERP
                canonical_symbol = f"{symbol}-PERP"
                
                event = NormalizedEvent(
                    id=event_id,
                    ts=ts,
                    source="metrics",
                    kind="market_snapshot",
                    symbol=canonical_symbol,
                    timeframe="1m",
                    payload=payload,
                    provenance=provenance,
                    hash=event_hash
                )
                
                await insert_event(event)

                
            # Wait for 60 seconds
            await asyncio.sleep(60)
            
        except Exception as e:
            print(f"Hyperliquid Poller Error: {e}")
            await asyncio.sleep(60) # Wait before retrying
