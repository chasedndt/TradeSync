import asyncio
import sys
import os
from unittest.mock import MagicMock, AsyncMock

# Add path to find modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'services', 'ingest-gateway')))

# Mock db module before importing hyperliquid
sys.modules['app.db'] = MagicMock()
sys.modules['app.db'].persist_event = AsyncMock()

from sources.hyperliquid import poll_hyperliquid_markets

async def test_hyperliquid_polling():
    print("Testing Hyperliquid Polling...")
    
    # We want to run the poller for one iteration then stop
    # Since it's an infinite loop, we can't easily stop it without modifying code or raising exception
    # But for verification, we can just run it and cancel it after a few seconds?
    # Or better, we can mock asyncio.sleep to raise an exception to break the loop
    
    try:
        # Start the poller
        task = asyncio.create_task(poll_hyperliquid_markets())
        
        # Wait a bit for it to make the request
        # We use wait_for to enforce timeout
        try:
            await asyncio.wait_for(asyncio.sleep(5), timeout=15)
        except asyncio.TimeoutError:
            pass # Should not happen if sleep(5) < timeout(15)
        
        # Check if persist_event was called
        if sys.modules['app.db'].persist_event.called:
            print("SUCCESS: persist_event was called!")
            call_args = sys.modules['app.db'].persist_event.call_args
            print(f"Call args: {call_args}")
        else:
            print("FAILURE: persist_event was NOT called.")
            
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
            
    except Exception as e:
        print(f"Test Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_hyperliquid_polling())
