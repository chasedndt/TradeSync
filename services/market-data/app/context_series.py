"""Collapse irregular context samples onto candle boundaries.

The Market Canvas draws funding and open interest underneath price. Both arrive
on their own clocks and neither matches the chart:

- Funding is published hourly by the venue.
- Open interest is sampled by our own context poller, several times a minute,
  and often with the same value repeated within the same second because one
  poll produces several events and each one writes a point.

A chart pane needs one value per candle, aligned to the candle open, or the
series will not line up with the bars above it. This module does that alignment
and nothing else, so the rule it enforces can be tested directly:

**A bucket with no sample in it is absent, not zero and not interpolated.**

That is the same rule the candle path follows — a gap in venue history stays a
gap — and it matters more here, because a flat line drawn through a collection
outage looks exactly like a market that did not move.
"""

from __future__ import annotations

from typing import Any, Iterable, Literal, Mapping, Sequence

Statistic = Literal["last", "sum", "mean", "max"]


def bucket_open(ts_ms: int, bucket_s: int) -> int:
    """The candle open, in seconds, that ``ts_ms`` falls inside."""
    return (ts_ms // 1000 // bucket_s) * bucket_s


def bucket_series(
    points: Iterable[Mapping[str, Any]],
    bucket_s: int,
    statistic: Statistic = "last",
    *,
    value_key: str = "value",
    ts_key: str = "ts",
) -> list[dict[str, float]]:
    """Collapse ``{ts, value}`` samples onto ``bucket_s`` boundaries.

    ``statistic`` says what a bucket holding several samples reports:

    - ``last``  the newest sample. Right for a *level* such as open interest:
                the answer to "what was it at the close of this candle".
    - ``sum``   the total. Right for a *flow* such as funding paid, where a 1d
                bucket covering 24 hourly rates should report the day's cost,
                not one hour of it.
    - ``mean``  the average. Right for a rate you want smoothed rather than
                accumulated.
    - ``max``   the largest. Kept for peak measures.

    Buckets with no sample are omitted entirely.
    """
    if bucket_s <= 0:
        raise ValueError("bucket_s must be positive")

    grouped: dict[int, list[tuple[int, float]]] = {}
    for point in points:
        try:
            ts_ms = int(point[ts_key])
            value = float(point[value_key])
        except (KeyError, TypeError, ValueError):
            # A malformed sample is dropped rather than defaulted to zero: a
            # zero funding rate is a claim about the market, and we do not have
            # the evidence to make it.
            continue
        grouped.setdefault(bucket_open(ts_ms, bucket_s), []).append((ts_ms, value))

    out: list[dict[str, float]] = []
    for time_s in sorted(grouped):
        samples = grouped[time_s]
        values = [value for _, value in samples]
        if statistic == "last":
            value = max(samples, key=lambda pair: pair[0])[1]
        elif statistic == "sum":
            value = sum(values)
        elif statistic == "mean":
            value = sum(values) / len(values)
        elif statistic == "max":
            value = max(values)
        else:
            raise ValueError(f"unknown statistic '{statistic}'")
        out.append({"time": time_s, "value": value, "samples": len(samples)})
    return out


def describe_coverage(
    series: Sequence[Mapping[str, Any]],
    candle_times: Sequence[int],
) -> dict[str, Any]:
    """How much of the chart window this series actually covers.

    The pane states this rather than drawing a confident line across a hole.
    ``first_time``/``last_time`` are the real extent of the data, which for
    open interest is bounded by our own 24-hour recording window and will
    usually be shorter than the candles above it.
    """
    if not candle_times:
        return {
            "candles": 0,
            "covered": 0,
            "coverage_pct": 0.0,
            "first_time": None,
            "last_time": None,
        }

    covered = {int(point["time"]) for point in series}
    matched = sum(1 for time_s in candle_times if time_s in covered)
    times = sorted(covered) if covered else []
    return {
        "candles": len(candle_times),
        "covered": matched,
        "coverage_pct": round(matched / len(candle_times) * 100, 1),
        "first_time": times[0] if times else None,
        "last_time": times[-1] if times else None,
    }
