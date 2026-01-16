import asyncio
import random
from ..models.market import MarketSnapshot
from ..ingest import ingest_market_snapshot

async def collect_hyperliquid():
    """
    Simulates collecting market data from Hyperliquid and ingesting it.
    In a real implementation, this would poll the Hyperliquid API.
    """
    # Simulated data
    snapshot = MarketSnapshot(
        source="hyperliquid",
        symbol="BTC-USD",
        mark=95000.0 + random.random() * 100,
        funding=0.0001,
        oi=1000000.0,
        volume=50000000.0,
        raw={"mock": "data", "exchange": "hyperliquid"}
    )
    
    await ingest_market_snapshot(snapshot)

if __name__ == "__main__":
    asyncio.run(collect_hyperliquid())
