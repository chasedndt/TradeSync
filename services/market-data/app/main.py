"""
Market Data Service - Phase 3B

Main entry point that runs:
1. Provider pollers (rate-limited)
2. Normalizer (raw -> normalized)
3. Snapshotter (normalized -> snapshots with regimes)
4. Alert emitter (regime changes)
"""

import httpx
import time
import os
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .redis_client import redis_client
from .providers import HyperliquidProvider
from .processors import MarketNormalizer, MarketSnapshotter
from .rate_limiter import rate_limiters
from .spot_premium import (
    COINBASE_TICKER_URL,
    coinbase_product_for,
    premium_bps,
    spot_mid,
)
from .context_series import bucket_series, describe_coverage
from .depth import summarise_book
from . import book_history
from . import liquidation_context
from .cross_venue import (
    BINANCE_OPEN_INTEREST_URL,
    BINANCE_PREMIUM_INDEX_URL,
    attach_cross_venue,
    binance_symbol_for,
    parse_open_interest,
    parse_premium_index,
)
from .news_tone import (
    BACKOFF_AFTER_429_S,
    GDELT_DOC_URL,
    MIN_REQUEST_SPACING_S,
    attach_news_tone,
    parse_timelinetone,
    query_for,
)
from .trade_flow import CVD_WINDOW_MS, TradeFlowTracker
from .trade_stream import run_trade_stream
from .candles import (
    DEFAULT_INTERVAL,
    DEFAULT_LIMIT,
    SUPPORTED_INTERVALS,
    CandleRequestError,
    normalize_candles,
    resolve_window,
)
from .feature_extractor import (
    RETURN_1H_ANCHOR_TOLERANCE_MS,
    RETURN_1H_WINDOW_MS,
    attach_derived_features,
    extract_feature_observations,
    load_sampling_intervals,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration
SYMBOLS = os.getenv("MARKET_SYMBOLS", "BTC-PERP,ETH-PERP,SOL-PERP").split(",")
ENABLE_HYPERLIQUID = os.getenv("ENABLE_HYPERLIQUID", "true").lower() == "true"

# Polling intervals (ms)
POLL_INTERVAL_CONTEXT = int(os.getenv("POLL_INTERVAL_CONTEXT", "5000"))
POLL_INTERVAL_ORDERBOOK = int(os.getenv("POLL_INTERVAL_ORDERBOOK", "3000"))
POLL_INTERVAL_FUNDING_HISTORY = int(os.getenv("POLL_INTERVAL_FUNDING_HISTORY", "300000"))  # 5 min
FUNDING_HISTORY_LOOKBACK_SECONDS = int(
    os.getenv("FUNDING_HISTORY_LOOKBACK_SECONDS", str(7 * 24 * 60 * 60))
)

# Global state
providers = []
normalizer = MarketNormalizer()
snapshotter = MarketSnapshotter()
background_tasks: List[asyncio.Task] = []
feature_sampling_intervals = load_sampling_intervals()
# Venue coin names, which is what the trade stream carries.
# Latest Coinbase spot mid per symbol: {symbol: (mid, observed_at_ms)}.
# Context only — an external reference venue, not the trading venue.
spot_reference: dict = {}
# Must be comfortably shorter than the premium's 10s alignment bound, or
# most snapshots find the spot reading already too old and the premium goes
# missing from the current snapshot while still accumulating history.
SPOT_POLL_INTERVAL_MS = int(os.getenv('SPOT_POLL_INTERVAL_MS', '3000'))

trade_flow = TradeFlowTracker(
    [s.replace('-PERP', '') for s in SYMBOLS], window_ms=CVD_WINDOW_MS
)


async def poll_spot_reference_loop():
    """Poll Coinbase spot for the premium reference.

    Failures are logged and skipped: this is Tier B context, and an outage at an
    external reference must never disturb Hyperliquid observation.
    """
    logger.info("Starting Coinbase spot reference poller")
    while True:
        try:
            async def read_one(client, symbol: str) -> None:
                product = coinbase_product_for(symbol)
                if not product:
                    return
                try:
                    response = await client.get(
                        COINBASE_TICKER_URL.format(product=product),
                        headers={"User-Agent": "tradesync/1.0"},
                        timeout=5.0,
                    )
                    response.raise_for_status()
                    mid = spot_mid(response.json())
                    if mid is not None:
                        # Stamped at the moment of the read, not the end of the
                        # batch, so alignment skew reflects this symbol only.
                        spot_reference[symbol] = (mid, int(time.time() * 1000))
                except Exception as exc:
                    logger.warning(f"Coinbase spot unavailable for {product}: {exc}")

            async with httpx.AsyncClient() as client:
                # Concurrently: read sequentially and the last symbol is always
                # the stalest, which showed up as an intermittently missing
                # premium on SOL.
                await asyncio.gather(*(read_one(client, s) for s in SYMBOLS))
        except Exception as exc:
            logger.warning(f"Spot reference poll failed: {exc}")
        await asyncio.sleep(SPOT_POLL_INTERVAL_MS / 1000)


# Latest Binance funding and open interest per symbol. External reference
# venue, context only; see cross_venue.py.
cross_venue_reference: dict = {}
CROSS_VENUE_POLL_INTERVAL_S = int(os.getenv("CROSS_VENUE_POLL_INTERVAL_S", "60"))
CROSS_VENUE_STALE_AFTER_MS = int(os.getenv("CROSS_VENUE_STALE_AFTER_MS", "600000"))


async def poll_cross_venue_loop():
    """Read Binance funding and OI for every symbol, concurrently, once a minute.

    Two public requests per coin per minute. A coin Binance does not list
    simply never gets a reading. Failures are logged and skipped: an external
    reference venue must never disturb Hyperliquid observation.
    """
    logger.info("Starting Binance cross-venue poller")
    while True:
        try:
            async def read_one(client, symbol: str) -> None:
                venue_symbol = binance_symbol_for(symbol)
                try:
                    premium_raw = await client.get(
                        BINANCE_PREMIUM_INDEX_URL, params={"symbol": venue_symbol}, timeout=8.0
                    )
                    premium_raw.raise_for_status()
                    premium = parse_premium_index(premium_raw.json())
                    if premium is None:
                        return
                    entry = cross_venue_reference.setdefault(symbol, {})
                    entry["premium"] = premium
                    oi_raw = await client.get(
                        BINANCE_OPEN_INTEREST_URL, params={"symbol": venue_symbol}, timeout=8.0
                    )
                    oi_raw.raise_for_status()
                    oi = parse_open_interest(oi_raw.json(), premium["mark_price_usd"])
                    if oi is not None:
                        entry["open_interest"] = oi
                except Exception as exc:
                    logger.warning(f"Binance unavailable for {venue_symbol}: {exc}")

            async with httpx.AsyncClient(headers={"User-Agent": "tradesync/1.0"}) as client:
                await asyncio.gather(*(read_one(client, s) for s in SYMBOLS))
        except Exception as exc:
            logger.warning(f"Cross-venue poll failed: {exc}")
        await asyncio.sleep(CROSS_VENUE_POLL_INTERVAL_S)


# Latest GDELT news tone per symbol. Context only; see news_tone.py.
news_tone_reference: dict = {}
NEWS_TONE_POLL_INTERVAL_S = int(os.getenv("NEWS_TONE_POLL_INTERVAL_S", "900"))
NEWS_TONE_STALE_AFTER_MS = int(os.getenv("NEWS_TONE_STALE_AFTER_MS", "3600000"))
NEWS_TONE_STARTUP_DELAY_S = int(os.getenv("NEWS_TONE_STARTUP_DELAY_S", "180"))


async def poll_news_tone_loop():
    """Ask GDELT for each coin's tone, one request at a time, spaced apart.

    GDELT's limit is one request every five seconds. Coins are polled
    sequentially with a gap, not concurrently, and a coin without a safe query
    is skipped. Failures are logged and skipped: Tier B context must never
    disturb Hyperliquid observation.
    """
    logger.info("Starting GDELT news tone poller")
    # Every redeploy used to fire a full cycle at once; several redeploys in an
    # afternoon read, to GDELT, like a burst. Wait before the first cycle.
    await asyncio.sleep(NEWS_TONE_STARTUP_DELAY_S)
    while True:
        try:
            async with httpx.AsyncClient() as client:
                for symbol in SYMBOLS:
                    query = query_for(symbol)
                    if not query:
                        continue
                    try:
                        response = await client.get(
                            GDELT_DOC_URL,
                            params={
                                "query": query,
                                "mode": "timelinetone",
                                # A day, not six hours: for smaller coins GDELT
                                # answers a six-hour window with an empty object.
                                # Freshness still governs what gets attached.
                                "timespan": "24h",
                                "format": "json",
                            },
                            headers={"User-Agent": "tradesync/1.0 (private research)"},
                            timeout=20.0,
                        )
                        if response.status_code == 429:
                            # GDELT's limit is per-IP and bursty; one refusal
                            # means back off well past the nominal spacing.
                            logger.warning(f"GDELT rate-limited on {symbol}; backing off {BACKOFF_AFTER_429_S:.0f}s")
                            await asyncio.sleep(BACKOFF_AFTER_429_S)
                            continue
                        response.raise_for_status()
                        reading = parse_timelinetone(response.json(), int(time.time() * 1000))
                        if reading is not None:
                            news_tone_reference[symbol] = reading
                        else:
                            body = response.text[:160].replace("\n", " ")
                            logger.warning(f"GDELT tone for {symbol}: no closed bucket in response ({body!r})")
                    except Exception as exc:
                        logger.warning(f"GDELT tone unavailable for {symbol}: {exc}")
                    await asyncio.sleep(MIN_REQUEST_SPACING_S)
        except Exception as exc:
            logger.warning(f"News tone poll failed: {exc}")
        await asyncio.sleep(NEWS_TONE_POLL_INTERVAL_S)


def attach_spot_premium(payload: dict) -> dict:
    """Attach the spot-versus-perp premium when both sides are aligned.

    Absent when no recent spot reading exists or the two venues were sampled too
    far apart. A missing premium is absent, never zero.
    """
    symbol = str(payload.get("symbol") or "")
    reference = spot_reference.get(symbol)
    mark = (payload.get("price") or {}).get("mark_price_usd")
    perp_ts = payload.get("ts")
    if not reference or not mark or not isinstance(perp_ts, int):
        return payload

    spot_price, spot_ts = reference
    result = premium_bps(spot_price, float(mark), spot_ts, perp_ts)
    if result is None:
        return payload
    payload.setdefault("derived", {})["coinbase_premium_bps"] = result
    return payload


def attach_trade_flow(payload: dict) -> dict:
    """Attach observed taker flow to the snapshot.

    Absent when no trade has been seen for this symbol yet. Zero would read as
    balanced flow, which is a different claim from having no observation.
    """
    symbol = str(payload.get("symbol") or "")
    coin = symbol.replace("-PERP", "")
    value = trade_flow.value(coin)
    if value is None:
        return payload
    derived = payload.setdefault("derived", {})
    derived["cvd_window_usd"] = {
        "value": value,
        "window_ms": CVD_WINDOW_MS,
        "trades_observed": trade_flow.observed(coin),
    }
    return payload


async def resolve_derived_features(payload) -> dict:
    """Attach history-backed derivations to a snapshot before it is stored."""
    venue = str(payload.get("venue") or "")
    symbol = str(payload.get("symbol") or "")
    if not venue or not symbol:
        return payload
    try:
        mark_history = await redis_client.get_feature_timeseries(
            venue,
            symbol,
            "hl_mark_price_usd",
            RETURN_1H_WINDOW_MS + RETURN_1H_ANCHOR_TOLERANCE_MS + 60_000,
        )
    except Exception as exc:  # pragma: no cover - transport failure path
        logger.warning(f"mark-price history unavailable for {symbol}: {exc}")
        return payload
    enriched = attach_news_tone(
        attach_spot_premium(
            attach_trade_flow(attach_derived_features(payload, mark_history))
        ),
        news_tone_reference,
        NEWS_TONE_STALE_AFTER_MS,
    )
    return attach_cross_venue(enriched, cross_venue_reference, CROSS_VENUE_STALE_AFTER_MS)


async def store_snapshot_and_features(snapshot):
    """Store the latest snapshot and its cadence-governed feature history."""
    payload = await resolve_derived_features(snapshot.model_dump())
    await redis_client.store_snapshot(snapshot.venue, snapshot.symbol, payload)
    for observation in extract_feature_observations(payload):
        interval = feature_sampling_intervals.get(observation["feature_id"], 0)
        if interval:
            await redis_client.append_feature_timeseries(
                observation["venue"],
                observation["symbol"],
                observation["feature_id"],
                observation["value"],
                observation["observed_at_ms"],
                interval,
            )


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
                            await store_snapshot_and_features(snapshot)

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
    """Poll orderbook data from all providers.

    Symbols are read concurrently, not one after another. The snapshot's
    timestamp is refreshed by this loop, and a sequential pass over ten
    symbols took about 25 seconds — so the first symbols in the list aged past
    Mission Control's 15-second freshness rule every cycle, as a staircase of
    ages (1s, 2s … 20s, 25s) showed on 2026-09-12. The venue rate limiter is
    still the throttle; concurrency only removes the self-inflicted queue.
    """
    logger.info(f"Starting orderbook poller for symbols: {SYMBOLS}")

    async def read_one(provider, symbol: str) -> None:
        try:
            orderbook = await provider.fetch_orderbook(symbol)
            if not orderbook:
                return
            try:
                await book_history.capture(redis_client.client, symbol, orderbook)
            except Exception as exc:
                logger.warning('Book history capture unavailable (%s)', type(exc).__name__)
            event = normalizer.normalize_orderbook(provider.venue, orderbook)
            if event:
                await redis_client.push_normalized(event.model_dump())
                snapshot = snapshotter.process_event(event)
                if snapshot:
                    await store_snapshot_and_features(snapshot)
        except Exception as e:
            logger.error(f"Error polling {provider.venue} orderbook for {symbol}: {e}")

    while True:
        try:
            for provider in providers:
                if not provider.enabled:
                    continue
                await asyncio.gather(*(read_one(provider, s) for s in SYMBOLS))

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
            # Fetch the feature catalog's seven-day funding comparison window.
            start_time = int((time.time() - FUNDING_HISTORY_LOOKBACK_SECONDS) * 1000)

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
                                await redis_client.append_feature_timeseries(
                                    event.venue,
                                    event.symbol,
                                    "hl_funding_hourly_rate",
                                    float(event.value.get("rate", 0)),
                                    event.ts,
                                    feature_sampling_intervals[
                                        "hl_funding_hourly_rate"
                                    ],
                                )

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


    if not providers:
        logger.warning("No providers enabled!")

    # Start background tasks
    background_tasks.append(asyncio.create_task(poll_context_loop()))
    background_tasks.append(asyncio.create_task(poll_orderbook_loop()))
    background_tasks.append(asyncio.create_task(poll_funding_history_loop()))
    background_tasks.append(asyncio.create_task(poll_spot_reference_loop()))
    background_tasks.append(asyncio.create_task(poll_news_tone_loop()))
    background_tasks.append(asyncio.create_task(poll_cross_venue_loop()))
    background_tasks.append(asyncio.create_task(liquidation_context.run(redis_client.client)))
    background_tasks.append(
        asyncio.create_task(
            run_trade_stream(trade_flow, [s.replace('-PERP', '') for s in SYMBOLS])
        )
    )

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


# A snapshot older than this means the pollers have stopped doing their job,
# whatever the HTTP server reports. Generous relative to the 5s context poll so
# a single slow cycle does not flap the container state.
SNAPSHOT_STALE_AFTER_SECONDS = int(os.getenv("SNAPSHOT_STALE_AFTER_SECONDS", "90"))
# Grace after startup, before any poll has completed.
READINESS_GRACE_SECONDS = int(os.getenv("READINESS_GRACE_SECONDS", "120"))
_started_at = time.time()


@app.get("/healthz")
async def healthz():
    """Liveness only: the process is up and serving.

    Deliberately does not assert data freshness. Use /readyz for that; keeping
    the two separate means a stale-data condition is visible as exactly that,
    rather than looking like a dead process.
    """
    return {"ok": True, "service": "market-data"}


async def readiness_report() -> dict:
    """Whether this service is actually doing its job.

    On 2026-09-07 the pollers stopped for an hour while Redis refused writes.
    `/healthz` answered 200 throughout and Docker reported the container
    healthy, so the outage was invisible until the dashboard was inspected by
    hand. A healthcheck that only proves the port is open will lie at exactly
    the moment the truth matters.
    """
    now = time.time()
    symbols: list[dict] = []
    stale: list[str] = []
    missing: list[str] = []

    for symbol in SYMBOLS:
        snapshot = None
        try:
            snapshot = await redis_client.get_snapshot("hyperliquid", symbol)
        except Exception as exc:  # transport failure is itself unreadiness
            symbols.append({"symbol": symbol, "state": "unreadable", "reason": str(exc)})
            missing.append(symbol)
            continue
        if not snapshot or not snapshot.get("ts"):
            symbols.append({"symbol": symbol, "state": "missing"})
            missing.append(symbol)
            continue
        age = round(now - snapshot["ts"] / 1000, 1)
        state = "fresh" if age <= SNAPSHOT_STALE_AFTER_SECONDS else "stale"
        if state == "stale":
            stale.append(symbol)
        symbols.append({"symbol": symbol, "state": state, "age_seconds": age})

    uptime = now - _started_at
    starting = uptime < READINESS_GRACE_SECONDS and (stale or missing)
    ready = not stale and not missing

    return {
        "ready": ready or starting,
        "starting": bool(starting),
        "reason": (
            ""
            if ready
            else "within startup grace period"
            if starting
            else f"stale: {', '.join(stale)}" if stale and not missing
            else f"missing: {', '.join(missing)}" if missing and not stale
            else f"stale: {', '.join(stale)}; missing: {', '.join(missing)}"
        ),
        "stale_after_seconds": SNAPSHOT_STALE_AFTER_SECONDS,
        "uptime_seconds": round(uptime, 1),
        "symbols": symbols,
    }


@app.get("/readyz")
async def readyz():
    """Readiness: fresh market observations are actually being stored."""
    report = await readiness_report()
    if not report["ready"]:
        return JSONResponse(status_code=503, content=report)
    return report


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
    """All current snapshots, in the configured symbol order.

    Redis returns keys in an arbitrary order, and the Cockpit now derives its
    symbol list from this response instead of a constant — so the order here
    is the order the operator sees everywhere. Anything not in MARKET_SYMBOLS
    (a symbol removed from the list whose key has not expired yet) sorts last.
    """
    rank = {symbol: index for index, symbol in enumerate(SYMBOLS)}
    snapshots = sorted(
        await redis_client.get_all_snapshots(),
        key=lambda s: (rank.get(s.get("symbol"), len(rank)), s.get("symbol", "")),
    )
    # Two different ages, stated separately. ``data_age_ms`` (set by the
    # snapshotter) is the age of the oldest *metric* inside the snapshot — a
    # completeness measure. ``snapshot_age_ms`` is how long since the venue
    # was last observed for the symbol at all — a liveness measure. Mission
    # Control judged "LIVE" on the first and read a healthy feed as stale.
    now_ms = int(time.time() * 1000)
    for snapshot in snapshots:
        ts = snapshot.get("ts")
        snapshot["snapshot_age_ms"] = max(0, now_ms - int(ts)) if isinstance(ts, int) else None
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


@app.get("/features/{venue}/{symbol}")
async def get_features(venue: str, symbol: str):
    """Extract current admitted feature values from the latest snapshot."""
    snapshot = await redis_client.get_snapshot(venue, symbol)
    if not snapshot:
        return JSONResponse(
            status_code=404,
            content={"error": "not_found", "venue": venue, "symbol": symbol},
        )
    observations = extract_feature_observations(snapshot)
    return {
        "venue": venue,
        "symbol": symbol,
        "observations": observations,
        "count": len(observations),
    }


FEATURE_HISTORY_WINDOWS_MS = {
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "24h": 24 * 60 * 60 * 1000,
    "7d": 7 * 24 * 60 * 60 * 1000,
}
DEFAULT_FEATURE_HISTORY_WINDOW_MS = FEATURE_HISTORY_WINDOWS_MS["7d"]
MAX_BATCH_FEATURE_IDS = 64
# Normalization never looks further back than a feature's lookback_points
# (168 today). A 7-day series holds thousands, so callers get a bounded
# tail by default rather than the whole store.
DEFAULT_SERIES_POINTS = 250


@app.get("/candles/{venue}/{symbol}")
async def get_candles(
    venue: str,
    symbol: str,
    interval: str = DEFAULT_INTERVAL,
    limit: int = DEFAULT_LIMIT,
    start_ms: int | None = None,
    end_ms: int | None = None,
):
    """Return venue OHLCV candles for the Market Canvas and outcome measurement.

    Display and annotation only. These never enter the feature catalog, so a
    chart cannot become a source of scoring authority.

    ``start_ms``/``end_ms`` select an explicit range instead of the latest
    ``limit`` candles, for measurements that need a window older than the
    most recent history.
    """
    if venue != "hyperliquid":
        return JSONResponse(
            status_code=404,
            content={"error": "unsupported_venue", "venue": venue},
        )

    try:
        resolved_interval, resolved_limit, start_ms, end_ms = resolve_window(
            interval, limit, start_ms=start_ms, end_ms=end_ms
        )
    except CandleRequestError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_request",
                "detail": str(exc),
                "supported_intervals": list(SUPPORTED_INTERVALS),
            },
        )

    provider = next((p for p in providers if p.venue == venue and p.enabled), None)
    if provider is None:
        return JSONResponse(
            status_code=503,
            content={"error": "provider_unavailable", "venue": venue},
        )

    raw = await provider.fetch_candles(symbol, resolved_interval, start_ms, end_ms)
    candles = normalize_candles(raw)
    return {
        "venue": venue,
        "symbol": symbol,
        "interval": resolved_interval,
        "requested": resolved_limit,
        "count": len(candles),
        "candles": candles,
        # Stated on every response so a consumer cannot mistake a chart for a
        # scoring input.
        "authority": "display_only",
    }


@app.get("/feature-histories/{venue}/{symbol}")
async def get_feature_histories(
    venue: str,
    symbol: str,
    feature_ids: str,
    window: str = "7d",
    points: int = DEFAULT_SERIES_POINTS,
):
    """Return several feature histories in one response.

    A regime evaluation needs one history per normalized feature. Fetching them
    individually costs one HTTP round trip each, per symbol, per cycle, which
    saturated this service as the catalog grew. Batching keeps that cost flat.
    """
    requested = [part.strip() for part in feature_ids.split(",") if part.strip()]
    if not requested:
        return JSONResponse(
            status_code=400,
            content={"error": "feature_ids_required", "venue": venue, "symbol": symbol},
        )
    if len(requested) > MAX_BATCH_FEATURE_IDS:
        return JSONResponse(
            status_code=400,
            content={
                "error": "too_many_feature_ids",
                "limit": MAX_BATCH_FEATURE_IDS,
                "requested": len(requested),
            },
        )

    window_ms = FEATURE_HISTORY_WINDOWS_MS.get(
        window, DEFAULT_FEATURE_HISTORY_WINDOW_MS
    )
    series = {}
    for feature_id in requested:
        series[feature_id] = await redis_client.get_feature_timeseries(
            venue, symbol, feature_id, window_ms, limit=points
        )
    return {
        "venue": venue,
        "symbol": symbol,
        "window": window,
        "points": points,
        "series": series,
        "count": len(series),
    }


@app.get("/feature-history/{venue}/{symbol}/{feature_id}")
async def get_feature_history(
    venue: str,
    symbol: str,
    feature_id: str,
    window: str = "7d",
    points: int = 0,
):
    """Return cadence-governed feature history used by the shared normalizer.

    ``points`` bounds the response to the most recent N samples; 0 keeps the
    whole window, which remains useful for inspection and replay.
    """
    window_ms = FEATURE_HISTORY_WINDOWS_MS.get(
        window, DEFAULT_FEATURE_HISTORY_WINDOW_MS
    )
    data = await redis_client.get_feature_timeseries(
        venue, symbol, feature_id, window_ms, limit=points or None
    )
    return {
        "venue": venue,
        "symbol": symbol,
        "feature_id": feature_id,
        "window": window,
        "data": data,
        "count": len(data),
    }


@app.get("/alerts")
async def get_alerts(limit: int = 50):
    """Get recent market alerts."""
    alerts = await redis_client.get_alerts(limit)
    return {"alerts": alerts, "count": len(alerts)}


@app.get("/context/{venue}/{symbol}")
async def get_canvas_context(
    venue: str,
    symbol: str,
    interval: str = DEFAULT_INTERVAL,
    limit: int = DEFAULT_LIMIT,
):
    """Funding and open interest aligned to the candles the canvas is drawing.

    Two sources with two different reaches, reported separately rather than
    blended into one line:

    - **Funding** comes from the venue's own ``fundingHistory``. It is hourly,
      authoritative, and available for as far back as the chart goes.
    - **Open interest** comes from our own context poller. Hyperliquid publishes
      only the current value, so there is no history to ask for; ours is a
      rolling 24 hours and stops there. The response says how much of the
      window it actually covers so the pane can state the limit instead of
      drawing a line that quietly ends.

    Display only. Neither series enters the feature catalog from here.
    """
    if venue != "hyperliquid":
        return JSONResponse(
            status_code=404,
            content={"error": "unsupported_venue", "venue": venue},
        )

    try:
        resolved_interval, resolved_limit, start_ms, end_ms = resolve_window(
            interval, limit
        )
    except CandleRequestError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_request",
                "detail": str(exc),
                "supported_intervals": list(SUPPORTED_INTERVALS),
            },
        )

    provider = next((p for p in providers if p.venue == venue and p.enabled), None)
    if provider is None:
        return JSONResponse(
            status_code=503,
            content={"error": "provider_unavailable", "venue": venue},
        )

    bucket_s = SUPPORTED_INTERVALS[resolved_interval] // 1000
    candle_times = [
        (start_ms // 1000 // bucket_s) * bucket_s + index * bucket_s
        for index in range(resolved_limit + 1)
    ]

    # Funding is published once an hour. Judged against 15m candles it can never
    # score above 25% however complete it is, which would read as a data problem
    # that does not exist. It is measured against its own hourly grid instead;
    # open interest, which really is sampled per candle, keeps the candle grid.
    FUNDING_PERIOD_S = 3600
    funding_times = (
        candle_times
        if bucket_s >= FUNDING_PERIOD_S
        else [
            (start_ms // 1000 // FUNDING_PERIOD_S) * FUNDING_PERIOD_S
            + index * FUNDING_PERIOD_S
            for index in range((resolved_limit * bucket_s) // FUNDING_PERIOD_S + 1)
        ]
    )

    # Funding is a flow: over a bucket wider than an hour the meaningful number
    # is the total paid, not one hour of it picked out of the middle.
    # Paged across the whole window (Hyperliquid returns 500 rows per request) and cached per market.
    funding_raw = await provider.fetch_funding_history(symbol, start_ms, end_ms)
    funding = bucket_series(
        funding_raw,
        bucket_s,
        statistic="sum" if bucket_s > 3600 else "last",
        value_key="rate",
    )

    # Open interest is a level: the value standing at the close of the bucket.
    # The poller writes several identical points per poll, so "last" is also
    # what removes that duplication.
    oi_raw = await redis_client.get_timeseries(
        venue, symbol, "oi", end_ms - start_ms
    )
    open_interest = bucket_series(oi_raw, bucket_s, statistic="last")

    return {
        "venue": venue,
        "symbol": symbol,
        "interval": resolved_interval,
        "bucket_s": bucket_s,
        "funding": {
            "series": funding,
            "unit": "rate_per_hour" if bucket_s <= 3600 else "rate_summed_over_bucket",
            "source": "hyperliquid fundingHistory",
            "native_period_s": FUNDING_PERIOD_S,
            "coverage": describe_coverage(funding, funding_times),
        },
        "open_interest": {
            "series": open_interest,
            "unit": "usd",
            "source": "market-data context poller (rolling 24h)",
            "coverage": describe_coverage(open_interest, candle_times),
            "limit_note": (
                "Hyperliquid publishes only current open interest, so this is "
                "our own recording and reaches back at most 24 hours."
            ),
        },
        "authority": "display_only",
    }


@app.get("/depth/{venue}/{symbol}")
async def get_depth(venue: str, symbol: str):
    """The current L2 book as a cumulative ladder, plus any resting walls.

    A single poll, not a series: the book is replaced wholesale each time, so
    there is nothing here to draw across past candles.
    """
    if venue != "hyperliquid":
        return JSONResponse(
            status_code=404,
            content={"error": "unsupported_venue", "venue": venue},
        )

    provider = next((p for p in providers if p.venue == venue and p.enabled), None)
    if provider is None:
        return JSONResponse(
            status_code=503,
            content={"error": "provider_unavailable", "venue": venue},
        )

    book = summarise_book(await provider.fetch_orderbook(symbol))
    if book is None:
        return JSONResponse(
            status_code=503,
            content={
                "error": "book_unavailable",
                "venue": venue,
                "symbol": symbol,
                "detail": "The venue did not return a book; none is reconstructed.",
            },
        )
    return book


@app.get("/book-history/{symbol}")
async def get_book_history(symbol: str):
    if symbol not in SYMBOLS:
        return JSONResponse(status_code=404, content={"error": "unsupported_symbol"})
    return await book_history.history(redis_client.client, symbol)


@app.get("/liquidation-context/{symbol}")
async def get_liquidation_context(symbol: str):
    if symbol not in SYMBOLS:
        return JSONResponse(status_code=404, content={"error": "unsupported_symbol"})
    return await liquidation_context.history(redis_client.client, symbol)


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
