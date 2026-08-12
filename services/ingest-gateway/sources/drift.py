import asyncio
import uuid
import logging
import aiohttp
from datetime import datetime
from app.models import NormalizedEvent
from app.db import insert_event

# Configure logging
logger = logging.getLogger(__name__)

# Drift API Endpoint
# /contracts was removed from the Drift Data API (returns 404).
# Replacement: /stats/markets — returns {success, markets: [...]} with same logical data.
DRIFT_API_URL = "https://data.api.drift.trade/stats/markets"

async def fetch_drift_contracts():
    """
    Fetch market data from Drift API via /stats/markets.
    Returns a list of perp market dicts with symbol, funding, OI, price fields.
    """
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(DRIFT_API_URL) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch Drift markets: {response.status}")
                    return []
                data = await response.json()
                # /stats/markets returns {"success": true, "markets": [...]} or a bare list
                if isinstance(data, dict):
                    markets = data.get("markets", data.get("data", []))
                elif isinstance(data, list):
                    markets = data
                else:
                    logger.warning(f"Drift API returned unexpected format: {type(data)}")
                    return []
                # Only perp markets; remap field names to the shape downstream expects
                result = []
                for m in markets:
                    if m.get("marketType", "perp") != "perp":
                        continue
                    # Normalise fundingRate: scalar or {long, short}
                    fr = m.get("fundingRate", 0)
                    funding_rate = float(fr.get("long", 0) if isinstance(fr, dict) else (fr or 0))
                    # Normalise openInterest: scalar or {long, short}
                    oi_raw = m.get("openInterest", 0)
                    open_interest = (
                        float(oi_raw.get("long", 0)) + float(oi_raw.get("short", 0))
                        if isinstance(oi_raw, dict) else float(oi_raw or 0)
                    )
                    result.append({
                        "ticker_id": m.get("symbol", ""),
                        "last_price": m.get("price", 0),
                        "funding_rate": funding_rate,
                        "open_interest": open_interest,
                        "index_price": m.get("oraclePrice", 0),
                    })
                logger.info(f"Drift /stats/markets returned {len(result)} perp markets")
                return result
        except Exception as e:
            logger.error(f"Exception fetching Drift markets: {e}")
            return []

async def poll_drift_markets():
    """
    Poll Drift markets, filter for BTC, ETH, SOL, and insert snapshots into DB.
    """
    logger.info("Starting Drift market polling...")

    while True:
        try:
            contracts = await fetch_drift_contracts()

            # Filter for BTC, ETH, SOL perps
            target_bases = ["BTC", "ETH", "SOL"]

            for contract in contracts:
                # Fields: ticker_id, last_price, funding_rate, open_interest
                symbol = contract.get("ticker_id") # e.g. "BTC-PERP"

                if not symbol:
                    continue

                is_target = False
                for base in target_bases:
                    if symbol == f"{base}-PERP":
                        is_target = True
                        break

                if not is_target:
                    continue

                # Create payload
                payload = {
                    "mark": contract.get("last_price"),
                    "funding": contract.get("funding_rate"),
                    "oi": contract.get("open_interest"),
                    "index_price": contract.get("index_price"),
                    "venue": "drift"
                }
                
                ts = datetime.now()
                event_id = str(uuid.uuid4())
                
                event_hash = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"drift:{symbol}:{ts.isoformat()}"))
                
                event = NormalizedEvent(
                    id=event_id,
                    ts=ts,
                    source="metrics",
                    kind="market_snapshot",
                    symbol=symbol,
                    timeframe="1m",
                    payload=payload,
                    provenance={"method": "poll_drift_markets", "venue": "drift"},
                    hash=event_hash
                )
                
                await insert_event(event)
                logger.debug(f"Inserted Drift event for {symbol}")

            # Wait before next poll
            await asyncio.sleep(10) 
            
        except asyncio.CancelledError:
            logger.info("Drift polling cancelled.")
            break
        except Exception as e:
            logger.error(f"Error polling Drift markets: {e}")
            await asyncio.sleep(10)
