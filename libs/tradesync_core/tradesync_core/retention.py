"""Bound the refusal store without losing what refusals are for.

Every scoring pass records one verdict per symbol, admitted or refused. That is
correct — the dashboard has to be able to say *why* no opportunity exists — but
it is also about 4,300 rows a day of full evidence JSON, growing forever, and
nobody reconstructs an individual refusal from three weeks ago.

What does keep mattering is the **denominator**. "The coverage floor blocked 61%
of ETH verdicts last Tuesday" is only answerable if the refusals that were not
admitted are counted somewhere. Deleting them outright would silently improve
every admission statistic ever computed afterwards, which is the worst possible
failure mode for a system whose whole claim is that it does not flatter itself.

So a refusal is rolled up before it is deleted: one row per day, symbol and
reason, carrying the count and the score and coverage distribution. The rollup
is cheap enough to keep forever and answers every aggregate question the full
rows could. The full rows stay available for a recent window, where they are
actually read.

These functions are pure so the arithmetic can be tested without a database.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

# Long enough that "why did nothing fire this week" is answerable from the full
# rows, short enough that the store stays small. Overridable per deployment.
DEFAULT_REFUSAL_RETENTION_DAYS = 7

# A rollup this system will not delete. Retention applies to the full evidence
# rows only; the aggregate is the permanent record.
ROLLUP_TABLE = "signal_refusal_daily"


def retention_cutoff(
    retention_days: int = DEFAULT_REFUSAL_RETENTION_DAYS,
    now: datetime | None = None,
) -> datetime:
    """The instant before which refusals may be rolled up and removed.

    Refuses a non-positive window: a retention of zero would delete a refusal in
    the same pass that wrote it, and the dashboard would have nothing to explain
    the current state with.
    """
    if retention_days < 1:
        raise ValueError("retention_days must be at least 1")
    moment = now or datetime.now(timezone.utc)
    return moment - timedelta(days=retention_days)


def primary_reason(features: Mapping[str, Any]) -> str:
    """The code a refusal is filed under.

    ``rejection_reasons`` is a list: a verdict can fail the coverage floor and
    the direction band at once. Counting such a row under both codes would make
    the refusal totals sum to more than the number of refusals, and an exact
    denominator is the only reason this table exists. The first code is used —
    that is the order ``decide_paper_signal`` produced them in, so it is the
    first gate the evidence actually failed.

    Secondary codes are not lost; they are tallied per bucket in
    ``reason_codes``.
    """
    reasons = features.get("rejection_reasons")
    if isinstance(reasons, (list, tuple)):
        for reason in reasons:
            if isinstance(reason, Mapping):
                code = reason.get("code")
                if code:
                    return str(code)
            elif reason:
                return str(reason)
    # Older rows carried a single string under a different key.
    single = features.get("refusal_reason")
    return str(single) if single else "unstated"


def all_reason_codes(features: Mapping[str, Any]) -> list[str]:
    """Every code on a refusal, in the order it was recorded."""
    reasons = features.get("rejection_reasons")
    codes: list[str] = []
    if isinstance(reasons, (list, tuple)):
        for reason in reasons:
            if isinstance(reason, Mapping):
                code = reason.get("code")
                if code:
                    codes.append(str(code))
            elif reason:
                codes.append(str(reason))
    if codes:
        return codes
    single = features.get("refusal_reason")
    return [str(single)] if single else ["unstated"]


def rollup_refusals(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate refusal rows into one entry per (day, symbol, primary reason).

    Each row needs ``created_at``, ``symbol`` and a ``features`` mapping holding
    ``rejection_reasons``, ``weighted_score`` and ``data_coverage``. A row with
    no stated reason is counted under ``unstated`` rather than dropped — losing
    it would understate the denominator, which is precisely what this exists to
    prevent.

    Returned entries are sorted so a batch writes deterministically.
    """
    buckets: dict[tuple[date, str, str], list[Mapping[str, Any]]] = defaultdict(list)

    for row in rows:
        created = row.get("created_at")
        if not isinstance(created, datetime):
            continue
        features = row.get("features") or {}
        if not isinstance(features, Mapping):
            features = {}
        symbol = str(row.get("symbol") or "unknown")
        buckets[(created.date(), symbol, primary_reason(features))].append(features)

    out: list[dict[str, Any]] = []
    for (day, symbol, reason), entries in sorted(buckets.items()):
        scores = _numbers(entries, "weighted_score")
        coverages = _numbers(entries, "data_coverage")
        codes: dict[str, int] = {}
        for features in entries:
            for code in all_reason_codes(features):
                codes[code] = codes.get(code, 0) + 1
        out.append(
            {
                "day": day,
                "symbol": symbol,
                "reason": reason,
                "refusals": len(entries),
                # Every code seen in this bucket, primary or not. Counts here
                # may exceed "refusals" because one verdict can fail several
                # gates; "refusals" is the one that stays exact.
                "reason_codes": codes,
                # None rather than 0.0 when nothing carried the field: a mean of
                # zero is a claim about the scores, and an absent field is not.
                "mean_score": _mean(scores),
                "mean_coverage": _mean(coverages),
                "min_coverage": min(coverages) if coverages else None,
                "max_coverage": max(coverages) if coverages else None,
                # Two counts, not one. A refusal can carry a coverage without a
                # score, and weighting the coverage mean by the score count
                # would discard it entirely.
                "scored_rows": len(scores),
                "covered_rows": len(coverages),
            }
        )
    return out


def _numbers(entries: Iterable[Mapping[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for entry in entries:
        value = entry.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.append(float(value))
    return values


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 6) if values else None


def merge_rollup(
    existing: Mapping[str, Any] | None,
    incoming: Mapping[str, Any],
) -> dict[str, Any]:
    """Combine a new rollup with one already stored for the same key.

    A retention pass can run twice inside one day, so the second batch must add
    to the first rather than replace it. Each mean is recombined weighted by the
    count of rows that carried *that* measure, so a 5-row batch cannot pull a
    500-row day's average halfway toward itself, and a batch that carried a
    coverage but no score still contributes its coverage.
    """
    if existing is None:
        return dict(incoming)

    total = int(existing["refusals"]) + int(incoming["refusals"])
    scored = int(existing.get("scored_rows") or 0) + int(incoming.get("scored_rows") or 0)
    covered = int(existing.get("covered_rows") or 0) + int(incoming.get("covered_rows") or 0)

    return {
        "day": incoming["day"],
        "symbol": incoming["symbol"],
        "reason": incoming["reason"],
        "refusals": total,
        "reason_codes": _merge_counts(
            existing.get("reason_codes"), incoming.get("reason_codes")
        ),
        "mean_score": _weighted(
            existing.get("mean_score"),
            existing.get("scored_rows") or 0,
            incoming.get("mean_score"),
            incoming.get("scored_rows") or 0,
        ),
        "mean_coverage": _weighted(
            existing.get("mean_coverage"),
            existing.get("covered_rows") or 0,
            incoming.get("mean_coverage"),
            incoming.get("covered_rows") or 0,
        ),
        "min_coverage": _extreme(
            existing.get("min_coverage"), incoming.get("min_coverage"), min
        ),
        "max_coverage": _extreme(
            existing.get("max_coverage"), incoming.get("max_coverage"), max
        ),
        "scored_rows": scored,
        "covered_rows": covered,
    }


def _merge_counts(
    left: Mapping[str, int] | None, right: Mapping[str, int] | None
) -> dict[str, int]:
    merged: dict[str, int] = dict(left or {})
    for code, count in (right or {}).items():
        merged[code] = merged.get(code, 0) + int(count)
    return merged


def _weighted(
    left: float | None, left_n: int, right: float | None, right_n: int
) -> float | None:
    if left is None and right is None:
        return None
    if left is None:
        return right
    if right is None:
        return left
    total = left_n + right_n
    if total <= 0:
        return None
    return round((left * left_n + right * right_n) / total, 6)


def _extreme(left: float | None, right: float | None, pick) -> float | None:
    if left is None:
        return right
    if right is None:
        return left
    return pick(left, right)
