import asyncio
import random
from ..models.market import MarketSnapshot
from ..ingest import ingest_market_snapshot

async def collect_drift():
    """
    Simulates collecting market data from Drift and ingesting it.
    In a real implementation, this would poll the Drift API.
    """
    # Simulated data
    snapshot = MarketSnapshot(
        source="drift",
        symbol="SOL-USD",
        mark=150.0 + random.random() * 2,
        funding=0.0002,
        oi=500000.0,
        volume=10000000.0,
        raw={"mock": "data", "exchange": "drift"}
    )
    
    await ingest_market_snapshot(snapshot)

if __name__ == "__main__":
    asyncio.run(collect_drift())
