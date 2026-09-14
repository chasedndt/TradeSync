"""Why the Regime Lab's coverage is what it is: every reading's age, reason and feed.

Each feature result is annotated with its reading's age against the feature's
own stale limit, the feed it comes from, whether it is fresh, and one coverage
reason, checked in this order:

- ``unavailable``: no current reading at all;
- ``display_only``: a value shown for context and never normalized;
- ``stale``: a reading at or past its stale limit (a limit of zero never counts as fresh);
- ``collecting_history``: fewer prior readings than the catalog's minimum;
- ``fresh``: normalized and within its stale limit;
- ``flat``: every recent value identical, so there is no dispersion to score;
- ``unavailable``: anything else the normalizer refused, with its reason kept.

The overview's health summary counts those reasons, counts the fresh readings
(the only ones called live), and gives each feed its newest reading's age set
against the tightest stale limit among the feed's features.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

REASONS = ("fresh", "stale", "flat", "collecting_history", "display_only", "unavailable")

# Matched in order against the catalog's ``source`` text; the first match names the feed.
FEEDS = (
    ("l2book", "Hyperliquid order book"),
    ("trades websocket", "Hyperliquid trades"),
    ("coinbase", "Coinbase"),
    ("binance", "Binance"),
    ("gdelt", "GDELT"),
    ("open-interest", "Hyperliquid market context"),
    ("hyperliquid", "Hyperliquid market context"),
)
NO_ADAPTER = "No live adapter"


def feed_of(definition: Mapping[str, Any]) -> str:
    source = str(definition.get("source") or "").lower()
    return next((feed for needle, feed in FEEDS if needle in source), NO_ADAPTER)


def coverage_reason(result: Mapping[str, Any], freshness: str) -> str:
    if freshness == "missing":
        return "unavailable"
    status = result.get("status")
    if status == "not_normalized":
        return "display_only"
    if freshness == "stale" or status == "stale":
        return "stale"
    if status == "collecting_history":
        return "collecting_history"
    if status == "ready":
        return "fresh"
    if str(result.get("reason") or "").startswith("flat:"):
        return "flat"
    return "unavailable"


def annotate(
    result: Mapping[str, Any],
    definition: Mapping[str, Any],
    observed_at_ms: int | None,
    now_ms: int,
) -> dict[str, Any]:
    """``result`` with feed, age, stale limits, freshness and coverage reason."""
    stale_after = int(definition.get("stale_after_ms") or 0)
    age = None if observed_at_ms is None else max(0, now_ms - int(observed_at_ms))
    if age is None:
        freshness = "missing"
    elif stale_after > 0 and age < stale_after:
        freshness = "fresh"
    else:
        freshness = "stale"
    return {
        **result,
        "feed": feed_of(definition),
        "age_ms": age,
        "fresh_after_ms": int(definition.get("fresh_after_ms") or 0),
        "stale_after_ms": stale_after,
        "freshness": freshness,
        "coverage_reason": coverage_reason(result, freshness),
    }


def _feed_status(feed: Mapping[str, Any]) -> str:
    if not feed["observed"]:
        return "missing"
    if not feed["stale"]:
        return "fresh"
    return "stale" if not feed["fresh"] else "partly_stale"


def summarize(
    feature_results: Sequence[Mapping[str, Any]],
    source_status: Mapping[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    reasons = {reason: 0 for reason in REASONS}
    feeds: dict[str, dict[str, Any]] = {}
    fresh = 0
    for result in feature_results:
        reason = result.get("coverage_reason") or "unavailable"
        reasons[reason] = reasons.get(reason, 0) + 1
        freshness = result.get("freshness") or "missing"
        fresh += freshness == "fresh"
        name = result.get("feed") or NO_ADAPTER
        feed = feeds.setdefault(
            name,
            {"feed": name, "features": 0, "observed": 0, "fresh": 0, "stale": 0, "newest_age_ms": None, "stale_after_ms": None},
        )
        feed["features"] += 1
        if freshness == "missing":
            continue
        feed["observed"] += 1
        feed[freshness] += 1
        age, limit = result.get("age_ms"), result.get("stale_after_ms")
        if age is not None and (feed["newest_age_ms"] is None or age < feed["newest_age_ms"]):
            feed["newest_age_ms"] = age
        if limit and (feed["stale_after_ms"] is None or limit < feed["stale_after_ms"]):
            feed["stale_after_ms"] = limit
    for feed in feeds.values():
        feed["status"] = _feed_status(feed)
    market_status = source_status.get("status") or "unavailable"
    return {
        "evaluated_at_ms": now_ms,
        "market_data": {
            "status": market_status,
            "reason": source_status.get("reason"),
            "observation_count": int(source_status.get("observation_count") or 0),
        },
        "live": market_status == "live" and fresh > 0,
        "fresh_features": fresh,
        "feature_count": len(feature_results),
        "coverage_reasons": reasons,
        "feeds": sorted(feeds.values(), key=lambda feed: (feed["status"] == "missing", feed["feed"])),
    }
