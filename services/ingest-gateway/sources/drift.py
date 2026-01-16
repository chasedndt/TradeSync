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
# Using the one user provided: GET https://data.api.drift.trade/contracts
# But user said "contracts" returns contract info including OI and funding.
DRIFT_API_URL = "https://data.api.drift.trade/contracts"

async def fetch_drift_contracts():
    """
    Fetch contracts from Drift API.
    """
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(DRIFT_API_URL) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch Drift contracts: {response.status}")
                    return []
                # The response is likely a list of contracts or a dict with a list.
                # Assuming list based on "contracts" endpoint name, but let's handle dict too.
                data = await response.json()
                if isinstance(data, dict):
                    if "contracts" in data:
                        logger.info(f"Drift API returned dict with contracts key. Count: {len(data['contracts'])}")
                        return data["contracts"]
                    if "data" in data:
                        logger.info(f"Drift API returned dict with data key. Count: {len(data['data'])}")
                        return data["data"]
                    else:
                        logger.warning(f"Drift API returned dict with keys: {list(data.keys())}")
                        return []
                if isinstance(data, list):
                    logger.info(f"Drift API returned list. Count: {len(data)}")
                    return data
                logger.warning(f"Drift API returned unexpected format: {type(data)}")
                return []
        except Exception as e:
            logger.error(f"Exception fetching Drift contracts: {e}")
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
                    # Check for exact match or suffix
                    # Drift symbols: "BTC-PERP", "SOL-PERP"
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
                    "raw": contract, # Optional: store raw for debugging
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
