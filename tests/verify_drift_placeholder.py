import asyncio
import os
import sys
import asyncpg
import json

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.ingest_gateway.sources.drift import poll_drift_markets
# Note: The import path might be tricky depending on how python path is set.
# If running from project root:
# python tests/verify_drift.py

# Env vars
PG_DSN = os.getenv("PG_DSN", "postgresql://tradesync:CHANGE_ME@localhost:5432/tradesync")

async def verify():
    print("Verifying Drift integration...")
    
    # 1. Check if we can fetch markets (by running the poller for a short time)
    # Actually, we can just import the fetch function if we want, but let's test the whole flow.
    # But poll_drift_markets is an infinite loop.
    # We can run it as a task, wait a bit, then cancel it.
    
    # However, we need to make sure the DB is accessible.
    try:
        conn = await asyncpg.connect(PG_DSN)
        # Clean up old drift events for testing?
        # await conn.execute("DELETE FROM events WHERE source = 'drift'")
        # Maybe not, just check for new ones.
        
        # Count before
        count_before = await conn.fetchval("SELECT COUNT(*) FROM events WHERE source = 'drift'")
        print(f"Drift events before: {count_before}")
        await conn.close()
    except Exception as e:
        print(f"DB Connection failed: {e}")
        return

    # Start poller
    # We need to mock insert_event or let it run against real DB.
    # Let's run against real DB as requested.
    
    # We need to handle the infinite loop.
    # We can modify poll_drift_markets to accept a 'run_once' flag or just cancel it.
    # Or just run it in a task and cancel after 15 seconds.
    
    # But wait, imports might fail if not running as module.
    # Let's try to run this script.
    
    pass

if __name__ == "__main__":
    # This script is just a placeholder. 
    # I will run the actual verification by running the app or a specific test command.
    pass
