"""News tone per coin from the GDELT DOC 2.0 API, as a context-only feature.

GDELT indexes world news in 65 languages and scores each article's tone from
-100 to +100. Its ``timelinetone`` mode returns that tone averaged into
15-minute buckets for a query. Terms of use, read 2026-09-12: unrestricted use
for any purpose, free, no key, citation required — the cleanest-licensed news
source the research found.

Two constraints shape everything here:

- **One request every five seconds**, by GDELT's own limit (the API answers
  429 with that sentence). The poller asks for one coin at a time, spaced
  apart, on a fifteen-minute cycle; ten coins is ten requests per cycle.
- **Context only.** Tone is a candidate directional input whose skill has not
  been measured. It enters the catalog with ``scoring_eligible: false`` and is
  recorded against outcomes; it can earn a weight only through that record.

The GDELT Project: https://www.gdeltproject.org/
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
# GDELT asks for one request per five seconds, but in practice refused four of
# ten requests spaced six seconds apart on 2026-09-12. Fifteen seconds, with a
# two-minute back-off on any refusal, gets a clean cycle; ten coins take about
# three minutes, well inside the fifteen-minute cadence.
MIN_REQUEST_SPACING_S = 15.0
BACKOFF_AFTER_429_S = 120.0
BUCKET_S = 900  # GDELT tone timelines are 15-minute buckets

# What to ask GDELT for each coin. Ticker symbols alone are too ambiguous
# ("NEAR", "LINK", "UNI" are ordinary words), so each query names the project.
QUERIES: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "HYPE": '"hyperliquid"',
    "ZEC": "zcash",
    "XRP": '(XRP OR "ripple")',
    "NEAR": '"NEAR protocol"',
    "PUMP": '"pump.fun"',
    "LINK": "chainlink",
    "UNI": '"uniswap"',
    "DOGE": "dogecoin",
    "SUI": '"sui network"',
    "ARB": '"arbitrum"',
}


def query_for(symbol: str) -> str | None:
    """The GDELT query for a symbol, or None if the coin has no safe query."""
    return QUERIES.get(symbol.replace("-PERP", "").upper())


def _parse_bucket(stamp: Any) -> int | None:
    """``20260912T054500Z`` -> epoch milliseconds, or None if malformed."""
    if not isinstance(stamp, str):
        return None
    try:
        return int(datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000)
    except ValueError:
        return None


def parse_timelinetone(payload: Any, now_ms: int) -> dict[str, Any] | None:
    """The newest *closed* tone bucket from a ``timelinetone`` response.

    The last bucket in the timeline is usually the one still being filled; it
    is skipped, because a half-full bucket's average moves with every article
    and would read as tone changing when only the sample was growing. Returns
    None rather than a default when the payload is not the expected shape.
    """
    if not isinstance(payload, Mapping):
        return None
    timeline = payload.get("timeline")
    if not isinstance(timeline, list) or not timeline:
        return None
    series = timeline[0] if isinstance(timeline[0], Mapping) else None
    points = series.get("data") if series else None
    if not isinstance(points, list):
        return None

    parsed: list[tuple[int, float]] = []
    for point in points:
        if not isinstance(point, Mapping):
            continue
        at = _parse_bucket(point.get("date"))
        value = point.get("value")
        if at is None or isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        parsed.append((at, float(value)))
    if not parsed:
        return None
    parsed.sort()

    # Closed means the bucket's end lies in the past. A bucket GDELT found no
    # articles for comes back as exactly 0, not as a gap; a real average of
    # many articles' tones is never exactly zero. Exactly-zero buckets are
    # therefore "no news", which is absent — not "neutral news", which would
    # be a claim about the market.
    closed = [
        (at, value)
        for at, value in parsed
        if at + BUCKET_S * 1000 <= now_ms and value != 0.0
    ]
    if not closed:
        return None
    at, value = closed[-1]
    return {
        "value": value,
        "observed_at_ms": at,
        "bucket_end_ms": at + BUCKET_S * 1000,
        "buckets_seen": len(parsed),
        "source": "gdelt_doc_2_timelinetone",
    }


def attach_news_tone(payload: dict, reference: Mapping[str, Mapping[str, Any]], stale_after_ms: int) -> dict:
    """Write the latest tone reading onto a snapshot if it is still fresh.

    Absent, never zero, when there is no reading or it has aged out. A zero
    tone is a claim that the news was neutral; a missing one says nothing.
    """
    symbol = str(payload.get("symbol") or "")
    reading = reference.get(symbol)
    perp_ts = payload.get("ts")
    if not reading or not isinstance(perp_ts, int):
        return payload
    if perp_ts - int(reading["observed_at_ms"]) > stale_after_ms:
        return payload
    payload.setdefault("derived", {})["gdelt_news_tone"] = dict(reading)
    return payload
