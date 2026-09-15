"""Settled Hyperliquid funding for a paper position, hour by hour, from the venue's own history.

Hyperliquid settles funding every hour on the hour: position size × oracle price ×
funding rate, longs paying shorts when the rate is positive. A position takes part
in each settlement strictly after its entry and at or before its exit (or its last
observation while open). Each settlement used becomes a row: the published rate,
the price it was valued at and where that price came from, and the payment. An hour
whose rate is not published yet is listed as missing, never estimated, and the
summary says so.

Admission needs a cost budget before any settlement exists, so ``planning_bps_hour``
turns the funding rows observed before entry into an adverse hourly rate with a
declared floor. That number gates entries only; it never enters profit and loss.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

MODEL = "hyperliquid_settled_hourly_v1"
HOUR_S = 3600
MAX_PUBLISH_OFFSET_S = 120
PLANNING_ROWS = 24


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def settlement_hours(entry_time: float, until_time: float) -> list[int]:
    """Top-of-hour settlements a position took part in: after ``entry_time``, at or before ``until_time``."""
    first = (int(math.floor(entry_time)) // HOUR_S + 1) * HOUR_S
    last = int(math.floor(until_time)) // HOUR_S * HOUR_S
    return list(range(first, last + 1, HOUR_S))


def published_rates(rows: Iterable[Any]) -> dict[int, dict[str, float | None]]:
    """Venue rows ``[time_s, rate, premium]`` by settlement hour; rows far from an hour or not finite are skipped."""
    out: dict[int, dict[str, float | None]] = {}
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        at, rate = _finite(row[0]), _finite(row[1])
        premium = _finite(row[2]) if len(row) > 2 else None
        if at is None or at <= 0 or rate is None:
            continue
        hour = int(round(at / HOUR_S)) * HOUR_S
        if abs(at - hour) > MAX_PUBLISH_OFFSET_S:
            continue
        if hour in out and out[hour]["funding_rate"] != rate:
            raise ValueError(f"Conflicting funding rates published for settlement {hour}")
        out[hour] = {"funding_rate": rate, "premium": premium, "published_time": at}
    return out


def payment(side: str, quantity: float, price: float, rate: float) -> float:
    """What the position pays at one settlement; negative when it receives."""
    if side not in ("long", "short"):
        raise ValueError("Unsupported side")
    return (1 if side == "long" else -1) * quantity * price * rate + 0.0


def settle(side: str, quantity: float, hour: int, published: Mapping[str, Any], price: Mapping[str, Any]) -> dict[str, Any]:
    """One settlement row: the published rate valued at ``price`` (``value``, ``source``, ``observed_at``)."""
    value, size, rate = _finite(price.get("value")), _finite(quantity), _finite(published.get("funding_rate"))
    if value is None or value <= 0 or size is None or size <= 0 or rate is None:
        raise ValueError("Settlement needs a positive price and quantity and a finite rate")
    if hour % HOUR_S:
        raise ValueError("Settlements fall on the hour")
    return {"settled_at": hour, "funding_rate": rate, "premium": published.get("premium"), "side": side,
            "quantity": size, "price": value, "price_source": price.get("source"),
            "price_observed_at": price.get("observed_at"), "payment_usdc": payment(side, size, value, rate)}


def summary(entry_time: float, until_time: float, rows: Sequence[Mapping[str, Any]] | None) -> dict[str, Any]:
    """Funding so far: the rows for settlements in the window, their total, and any hour still unpublished."""
    expected = settlement_hours(entry_time, until_time)
    by_hour = {int(round(float(row["settled_at"]))): row for row in rows or []}
    used = [by_hour[hour] for hour in expected if hour in by_hour]
    missing = [hour for hour in expected if hour not in by_hour]
    return {"model": MODEL, "accrued_usdc": math.fsum(float(row["payment_usdc"]) for row in used),
            "settled_hours": len(used), "expected_hours": len(expected), "missing_hours": missing,
            "through": until_time, "status": "awaiting_rows" if missing else "complete"}


def planning_bps_hour(published: Mapping[int, Mapping[str, Any]], floor_bps_hour: float) -> dict[str, Any]:
    """An adverse hourly funding rate for the entry cost budget, from the latest settled rows seen before entry."""
    recent = [float(published[hour]["funding_rate"]) for hour in sorted(published)[-PLANNING_ROWS:]]
    mean_abs = math.fsum(abs(rate) for rate in recent) / len(recent) * 10_000 if recent else None
    above_floor = mean_abs is not None and mean_abs > floor_bps_hour
    return {"bps_hour": mean_abs if above_floor else floor_bps_hour,
            "basis": "mean_absolute_settled_rate" if above_floor else "declared_floor",
            "rows": len(recent), "mean_absolute_bps_hour": mean_abs, "floor_bps_hour": floor_bps_hour}


def planning_from_records(records: Iterable[Mapping[str, Any]], floor_bps_hour: float) -> dict[str, Any]:
    """``planning_bps_hour`` from frozen entry-evidence funding records (``observed_at``, ``funding_rate``)."""
    rows = [[record.get("observed_at"), record.get("funding_rate"), record.get("premium")] for record in records]
    return planning_bps_hour(published_rates(rows), floor_bps_hour)
