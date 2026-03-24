"""
Market Data Service - Phase 3B

Main entry point that runs:
1. Provider pollers (rate-limited)
2. Normalizer (raw -> normalized)
3. Snapshotter (normalized -> snapshots with regimes)
4. Alert emitter (regime changes)
"""

import os
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .redis_client import redis_client
from .providers import HyperliquidProvider, DriftProvider
from .processors import MarketNormalizer, MarketSnapshotter
from .rate_limiter import rate_limiters

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration
SYMBOLS = os.getenv("MARKET_SYMBOLS", "BTC-PERP,ETH-PERP,SOL-PERP").split(",")
ENABLE_HYPERLIQUID = os.getenv("ENABLE_HYPERLIQUID", "true").lower() == "true"
ENABLE_DRIFT = os.getenv("ENABLE_DRIFT", "true").lower() == "true"

# Polling intervals (ms)
POLL_INTERVAL_CONTEXT = int(os.getenv("POLL_INTERVAL_CONTEXT", "5000"))
POLL_INTERVAL_ORDERBOOK = int(os.getenv("POLL_INTERVAL_ORDERBOOK", "3000"))
POLL_INTERVAL_FUNDING_HISTORY = int(os.getenv("POLL_INTERVAL_FUNDING_HISTORY", "300000"))  # 5 min

# Global state
providers = []
normalizer = MarketNormalizer()
snapshotter = MarketSnapshotter()
background_tasks: List[asyncio.Task] = []


async def poll_context_loop():
    """Poll context data (funding, OI, volume) from all providers."""
    logger.info(f"Starting context poller for symbols: {SYMBOLS}")

    while True:
        try:
            for provider in providers:
                if not provider.enabled:
                    continue

                try:
                    # Fetch context data
                    raw_data = await provider.fetch_context(SYMBOLS)

                    if not raw_data:
                        continue

                    # Normalize
                    events = normalizer.normalize_context(provider.venue, raw_data)

                    # Push to Redis stream and update snapshots
                    for event in events:
                        # Push normalized event to stream
                        await redis_client.push_normalized(event.model_dump())

                        # Update snapshot
                        snapshot = snapshotter.process_event(event)
                        if snapshot:
                            # Store snapshot
                            await redis_client.store_snapshot(
                                snapshot.venue,
                                snapshot.symbol,
                                snapshot.model_dump()
                            )

                            # Check for regime changes
                            alerts = snapshotter.check_regime_change(
                                snapshot.venue,
                                snapshot.symbol,
                                snapshot.regimes
                            )
                            for alert in alerts:
                                await redis_client.push_alert(alert.model_dump())

                            # Append to timeseries
                            if snapshot.funding:
                                await redis_client.append_timeseries(
                                    snapshot.venue, snapshot.symbol,
                                    "funding", snapshot.funding.horizons.now,
                                    snapshot.ts
                                )
                            if snapshot.oi:
                                await redis_client.append_timeseries(
                                    snapshot.venue, snapshot.symbol,
                                    "oi", snapshot.oi.current_usd,
                                    snapshot.ts
                                )

                except Exception as e:
                    logger.error(f"Error polling {provider.venue} context: {e}")

            await asyncio.sleep(POLL_INTERVAL_CONTEXT / 1000)

        except asyncio.CancelledError:
            logger.info("Context poller cancelled")
            break
        except Exception as e:
            logger.error(f"Context poller error: {e}")
            await asyncio.sleep(5)


async def poll_orderbook_loop():
    """Poll orderbook data from all providers."""
    logger.info(f"Starting orderbook poller for symbols: {SYMBOLS}")

    while True:
        try:
            for provider in providers:
                if not provider.enabled:
                    continue

                for symbol in SYMBOLS:
                    try:
                        # Fetch orderbook
                        orderbook = await provider.fetch_orderbook(symbol)

                        if not orderbook:
                            continue

                        # Normalize
                        event = normalizer.normalize_orderbook(provider.venue, orderbook)

                        if event:
                            # Push to Redis
                            await redis_client.push_normalized(event.model_dump())

                            # Update snapshot
                            snapshot = snapshotter.process_event(event)
                            if snapshot:
                                await redis_client.store_snapshot(
                                    snapshot.venue,
                                    snapshot.symbol,
                                    snapshot.model_dump()
                                )

                    except Exception as e:
                        logger.error(f"Error polling {provider.venue} orderbook for {symbol}: {e}")

            await asyncio.sleep(POLL_INTERVAL_ORDERBOOK / 1000)

        except asyncio.CancelledError:
            logger.info("Orderbook poller cancelled")
            break
        except Exception as e:
            logger.error(f"Orderbook poller error: {e}")
            await asyncio.sleep(5)


async def poll_funding_history_loop():
    """Poll historical funding data periodically."""
    logger.info("Starting funding history poller")

    import time

    while True:
        try:
            # Fetch last 24 hours
            start_time = int((time.time() - 86400) * 1000)

            for provider in providers:
                if not provider.enabled:
                    continue

                for symbol in SYMBOLS:
                    try:
                        history = await provider.fetch_funding_history(symbol, start_time)

                        if history:
                            events = normalizer.normalize_funding_history(
                                provider.venue, symbol, history
                            )
                            for event in events:
                                # Just update snapshotter, don't flood Redis
                                snapshotter.process_event(event)

                    except Exception as e:
                        logger.error(f"Error fetching funding history: {e}")

            await asyncio.sleep(POLL_INTERVAL_FUNDING_HISTORY / 1000)

        except asyncio.CancelledError:
            logger.info("Funding history poller cancelled")
            break
        except Exception as e:
            logger.error(f"Funding history poller error: {e}")
            await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Market Data Service...")

    # Connect to Redis
    await redis_client.connect()

    # Initialize providers
    if ENABLE_HYPERLIQUID:
        providers.append(HyperliquidProvider())
        logger.info("Hyperliquid provider enabled")

    if ENABLE_DRIFT:
        providers.append(DriftProvider())
        logger.info("Drift provider enabled")

    if not providers:
        logger.warning("No providers enabled!")

    # Start background tasks
    background_tasks.append(asyncio.create_task(poll_context_loop()))
    background_tasks.append(asyncio.create_task(poll_orderbook_loop()))
    background_tasks.append(asyncio.create_task(poll_funding_history_loop()))

    logger.info("Market Data Service started")

    yield

    # Shutdown
    logger.info("Shutting down Market Data Service...")

    for task in background_tasks:
        task.cancel()

    await asyncio.gather(*background_tasks, return_exceptions=True)
    await redis_client.disconnect()

    logger.info("Market Data Service stopped")


# FastAPI app
app = FastAPI(
    title="TradeSync Market Data Service",
    version="0.1.0",
    description="Phase 3B - Market Data Expansion",
    lifespan=lifespan
)


@app.get("/healthz")
async def healthz():
    """Health check endpoint."""
    return {"ok": True, "service": "market-data"}


@app.get("/status")
async def status():
    """Get service status."""
    return {
        "providers": [
            {
                "venue": p.venue,
                "enabled": p.enabled,
                "metrics": p.get_supported_metrics()
            }
            for p in providers
        ],
        "symbols": SYMBOLS,
        "rate_limiters": rate_limiters.status()
    }


@app.get("/snapshots")
async def get_snapshots():
    """Get all current snapshots."""
    snapshots = await redis_client.get_all_snapshots()
    return {"snapshots": snapshots, "count": len(snapshots)}


@app.get("/snapshot/{venue}/{symbol}")
async def get_snapshot(venue: str, symbol: str):
    """Get snapshot for specific venue/symbol."""
    snapshot = await redis_client.get_snapshot(venue, symbol)
    if not snapshot:
        return JSONResponse(
            status_code=404,
            content={"error": "not_found", "venue": venue, "symbol": symbol}
        )
    return snapshot


@app.get("/alerts")
async def get_alerts(limit: int = 50):
    """Get recent market alerts."""
    alerts = await redis_client.get_alerts(limit)
    return {"alerts": alerts, "count": len(alerts)}


@app.get("/timeseries/{venue}/{symbol}/{metric}")
async def get_timeseries(
    venue: str,
    symbol: str,
    metric: str,
    window: str = "1h"
):
    """Get timeseries data for metric."""
    window_ms = {
        "5m": 5 * 60 * 1000,
        "15m": 15 * 60 * 1000,
        "1h": 60 * 60 * 1000,
        "4h": 4 * 60 * 60 * 1000,
        "24h": 24 * 60 * 60 * 1000,
    }.get(window, 60 * 60 * 1000)

    data = await redis_client.get_timeseries(venue, symbol, metric, window_ms)
    return {
        "venue": venue,
        "symbol": symbol,
        "metric": metric,
        "window": window,
        "data": data,
        "count": len(data)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
