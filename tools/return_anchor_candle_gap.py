#!/usr/bin/env python
"""How far a Hyperliquid 1-minute candle close sits from the mark price, and what that does to the 1-hour return.

The one-hour return falls back to a venue candle close as its anchor when
TradeSync holds no mark-price sample at t minus one hour
(``services/market-data/app/candle_anchor.py``). This measures that
substitution on recorded data, read-only, through the state API:

- the mark-price series, ``GET /state/regime-lab/feature-history`` (15-second
  samples, the newest 2,000, reported in whole seconds);
- 1-minute candles over the same span, ``GET /state/market/candles``.

For each candle the close is compared with the newest mark sample at or before
the candle's last millisecond (within 15 s). For each mark sample with both
anchors available one hour earlier, the return is computed both ways.

Usage:
    python tools/return_anchor_candle_gap.py [--base http://127.0.0.1:8000] [--out FILE]
"""

from __future__ import annotations

import argparse
import bisect
import json
import time
import urllib.parse
import urllib.request

HOUR_MS = 3_600_000
TOLERANCE_MS = 300_000
ALIGN_MS = 15_000
CANDLE_MS = 60_000


def get(base: str, path: str, **params) -> dict:
    url = f"{base}{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=120) as response:
        return json.load(response)


def newest_at_or_before(times: list[int], values: list[float], at_ms: int, within_ms: int) -> float | None:
    index = bisect.bisect_right(times, at_ms) - 1
    if index < 0 or times[index] < at_ms - within_ms:
        return None
    return values[index]


def quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * (len(ordered) - 1) + 0.5))]


def summary(close_diffs_bps: list[float], return_diffs_pp: list[float], agree: list[bool]) -> dict:
    absolute = [abs(d) for d in close_diffs_bps]
    absolute_pp = [abs(d) for d in return_diffs_pp]
    return {
        "candles_compared": len(close_diffs_bps),
        "close_minus_mark_bps": {
            "median_abs": quantile(absolute, 0.5),
            "p90_abs": quantile(absolute, 0.9),
            "mean_signed": sum(close_diffs_bps) / len(close_diffs_bps) if close_diffs_bps else None,
        },
        "returns_compared": len(return_diffs_pp),
        "return_candle_minus_mark_pp": {"median_abs": quantile(absolute_pp, 0.5), "p90_abs": quantile(absolute_pp, 0.9)},
        "return_sign_agreement": sum(agree) / len(agree) if agree else None,
    }


def measure_symbol(base: str, symbol: str) -> tuple[dict, list[float], list[float], list[bool]]:
    series = get(base, "/state/regime-lab/feature-history", symbol=symbol,
                 feature_ids="hl_mark_price_usd", window="24h", points=2000)["series"]["hl_mark_price_usd"]
    # Whole seconds: take each sample at the last millisecond it could have been observed.
    times = [int(sec) * 1000 + 999 for sec, _ in series]
    marks = [float(value) for _, value in series]
    candles: list[tuple[int, float]] = []
    start = (times[0] // CANDLE_MS) * CANDLE_MS
    while start < times[-1]:
        end = min(start + 1000 * CANDLE_MS, times[-1])
        rows = get(base, "/state/market/candles", venue="hyperliquid", symbol=symbol, interval="1m",
                   limit=1000, start_ms=start, end_ms=end).get("candles") or []
        candles += [(int(c["time"]) * 1000 + CANDLE_MS - 1, float(c["close"])) for c in rows]
        start = end
    candles = sorted({close_ms: price for close_ms, price in candles if close_ms < times[-1]}.items())
    close_times = [close_ms for close_ms, _ in candles]
    closes = [price for _, price in candles]

    close_diffs = []
    for close_ms, price in candles:
        mark = newest_at_or_before(times, marks, close_ms, ALIGN_MS)
        if mark:
            close_diffs.append((price / mark - 1) * 10_000)
    return_diffs, agree = [], []
    for at_ms, current in zip(times, marks):
        observed = newest_at_or_before(times, marks, at_ms - HOUR_MS, TOLERANCE_MS)
        candle = newest_at_or_before(close_times, closes, at_ms - HOUR_MS, TOLERANCE_MS)
        if observed and candle:
            r_mark, r_candle = (current / observed - 1) * 100, (current / candle - 1) * 100
            return_diffs.append(r_candle - r_mark)
            if r_mark and r_candle:
                agree.append((r_mark > 0) == (r_candle > 0))
    report = summary(close_diffs, return_diffs, agree)
    report["span_utc"] = [time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(times[0] / 1000)),
                          time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(times[-1] / 1000))]
    return report, close_diffs, return_diffs, agree


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--out")
    args = parser.parse_args()
    symbols = [s["symbol"] for s in get(args.base, "/state/market/snapshots")["snapshots"]]
    per_symbol, pooled = {}, ([], [], [])
    for symbol in symbols:
        report, close_diffs, return_diffs, agree = measure_symbol(args.base, symbol)
        per_symbol[symbol] = report
        pooled[0].extend(close_diffs), pooled[1].extend(return_diffs), pooled[2].extend(agree)
    result = {"measured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "pooled": summary(*pooled), "per_symbol": per_symbol}
    text = json.dumps(result, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
