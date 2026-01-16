import asyncio
import os
import sys
import asyncpg
import logging
import json

# Add project root to path
# Assuming script is in tests/ and project root is parent
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Add services/ingest-gateway to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../services/ingest-gateway')))

from sources.drift import poll_drift_markets
from app.db import insert_event # We might need this or just rely on drift using it.

# Env vars
PG_DSN = os.getenv("PG_DSN", "postgresql://tradesync:CHANGE_ME@localhost:5432/tradesync")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify():
    logger.info("Verifying Drift integration...")
    
    try:
        conn = await asyncpg.connect(PG_DSN)
        count_before = await conn.fetchval("SELECT COUNT(*) FROM events WHERE source = 'drift'")
        logger.info(f"Drift events before: {count_before}")
        await conn.close()
    except Exception as e:
        logger.error(f"DB Connection failed: {e}")
        return

    # Run poller for a short time
    task = asyncio.create_task(poll_drift_markets())
    
    logger.info("Running poller for 15 seconds...")
    await asyncio.sleep(15)
    
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Poller error: {e}")

    try:
        conn = await asyncpg.connect(PG_DSN)
        # Fetch the latest event
        row = await conn.fetchrow("SELECT payload FROM events WHERE source = 'drift' ORDER BY ts DESC LIMIT 1")
        if row:
            payload = json.loads(row['payload'])
            logger.info(f"Latest Drift Event Payload: {json.dumps(payload, indent=2)}")
            
            # Verify specific fields
            required_fields = ["mark", "funding", "oi"]
            missing = [f for f in required_fields if payload.get(f) is None]
            if missing:
                logger.error(f"Missing fields in payload: {missing}")
            else:
                logger.info("All required fields present.")
        else:
            logger.error("No Drift events found to inspect.")

        count_after = await conn.fetchval("SELECT COUNT(*) FROM events WHERE source = 'drift'")
        logger.info(f"Drift events after: {count_after}")
        await conn.close()
        
        if count_after > count_before:
            logger.info("SUCCESS: Drift events increased.")
        else:
            logger.error("FAILURE: No new Drift events found.")
            
    except Exception as e:
        logger.error(f"DB Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(verify())
