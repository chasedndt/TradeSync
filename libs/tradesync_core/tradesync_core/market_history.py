"""Rows for the durable market history tables, and the retention that downsamples them.

Pure: payloads from market-data in, database parameters out. One row per
minute per market (order books per aggregation), so a repeated recording pass
inserts nothing new, and retention can keep every fifteenth minute by
arithmetic on the timestamp alone.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

DEPTH_FULL_DAYS = 3
DEPTH_KEEP_DAYS = 90
OI_FULL_DAYS = 7
OI_KEEP_DAYS = 400
LIQUIDATIONS_KEEP_DAYS = 180
DOWNSAMPLED_MINUTES = 15


def minute(ms: float) -> datetime:
    """The UTC minute a millisecond timestamp falls in."""
    return datetime.fromtimestamp(int(ms // 60_000) * 60, timezone.utc)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _levels(rows: Any) -> list[list[float]]:
    out: list[list[float]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        price, size = _finite(row[0]), _finite(row[1])
        if price and size and price > 0 and size > 0:
            out.append([float(f"{price:.8g}"), round(size, 6)])
    return out


def depth_rows(symbol: str, books: Mapping[str, Mapping[str, Any]]) -> list[tuple[Any, ...]]:
    """(symbol, n_sig_figs, observed_at, mid, bids, asks) for each fresh aggregated book."""
    rows: list[tuple[Any, ...]] = []
    for book in books.values():
        if book.get("stale") or not isinstance(book.get("time_ms"), (int, float)):
            continue
        bids, asks = _levels(book.get("bids")), _levels(book.get("asks"))
        if not bids or not asks:
            continue
        mid = (bids[0][0] + asks[0][0]) / 2
        rows.append((symbol, int(book["n_sig_figs"]), minute(book["time_ms"]), mid, bids, asks))
    return rows


def open_interest_row(snapshot: Mapping[str, Any]) -> tuple[Any, ...] | None:
    """(symbol, observed_at, oi_usd, mark, oracle, funding, premium_bps, volume_24h) from a market-data snapshot."""
    price = snapshot.get("price") or {}
    oi = snapshot.get("oi") or {}
    funding = (snapshot.get("funding") or {}).get("horizons") or {}
    volume = (snapshot.get("volume") or {}).get("horizons") or {}
    # Stamp the row with when open interest was read, not when the snapshot was
    # assembled: a slow poll must not record an old value as fresh.
    oi_read = next((m.get("last_updated") for m in snapshot.get("available_metrics") or []
                    if isinstance(m, dict) and m.get("metric") == "oi"), None)
    ts, oi_usd, mark = _finite(oi_read), _finite(oi.get("current_usd")), _finite(price.get("mark_price_usd"))
    if not snapshot.get("symbol") or ts is None or oi_usd is None or oi_usd < 0 or not mark or mark <= 0:
        return None
    return (str(snapshot["symbol"]), minute(ts), oi_usd, mark, _finite(price.get("oracle_price_usd")),
            _finite(funding.get("now")), _finite(price.get("oracle_premium_bps")), _finite(volume.get("24h")))


def liquidation_rows(events: Sequence[Mapping[str, Any]]) -> list[tuple[Any, ...]]:
    """(source, event_id, symbol, event_time, side, price, size, notional, price_kind, received_at)."""
    rows: list[tuple[Any, ...]] = []
    for e in events:
        price, size, notional = _finite(e.get("price")), _finite(e.get("size")), _finite(e.get("notional_usd"))
        event_time, received = _finite(e.get("event_time")), _finite(e.get("received_at"))
        if (e.get("source") not in ("bybit", "binance", "okx") or e.get("position_side") not in ("long", "short")
                or e.get("price_kind") not in ("bankruptcy", "average_fill") or not e.get("id") or not e.get("symbol")
                or not price or not size or not notional or price <= 0 or size <= 0 or notional <= 0
                or event_time is None or received is None):
            continue
        rows.append((e["source"], str(e["id"]), str(e["symbol"]), datetime.fromtimestamp(event_time, timezone.utc),
                     e["position_side"], price, size, notional, e["price_kind"], datetime.fromtimestamp(received, timezone.utc)))
    return rows


def kept_after_downsampling(observed_at: datetime, now: datetime, full_days: int, keep_days: int) -> bool:
    """Every minute for ``full_days``, then every fifteenth minute until ``keep_days``, then nothing."""
    age_days = (now - observed_at).total_seconds() / 86400
    if age_days > keep_days:
        return False
    return age_days <= full_days or observed_at.minute % DOWNSAMPLED_MINUTES == 0


RETENTION_SQL: tuple[str, ...] = (
    f"DELETE FROM market_depth_snapshots WHERE observed_at < now() - interval '{DEPTH_KEEP_DAYS} days'",
    f"DELETE FROM market_depth_snapshots WHERE observed_at < now() - interval '{DEPTH_FULL_DAYS} days' "
    f"AND extract(minute from observed_at)::int % {DOWNSAMPLED_MINUTES} <> 0",
    f"DELETE FROM market_open_interest WHERE observed_at < now() - interval '{OI_KEEP_DAYS} days'",
    f"DELETE FROM market_open_interest WHERE observed_at < now() - interval '{OI_FULL_DAYS} days' "
    f"AND extract(minute from observed_at)::int % {DOWNSAMPLED_MINUTES} <> 0",
    f"DELETE FROM market_liquidation_events WHERE event_time < now() - interval '{LIQUIDATIONS_KEEP_DAYS} days'",
)
