"""Re-run the rulebook over a frozen window of stored evidence.

Every tuning decision before this existed was unfalsifiable: weights were
changed and the market moved on, so there was no way to tell whether an
improvement was the change or the day.

Replay holds the evidence still. Champion and challenger see byte-identical
block scores, qualities and directional readings; only the rulebook and the
admission policy differ. Any difference in outcome is therefore attributable to
the configuration and nothing else.

Two rules keep this honest:

- **Reuse the live code path.** ``evaluate_blocks`` and ``decide_paper_signal``
  are the same functions the producer calls. A separate replay implementation
  would eventually disagree with production and the replay would be measuring
  itself.
- **Never re-derive evidence.** Block scores are read from what was recorded at
  the time, not recomputed from today's feature history. Recomputing would leak
  information that did not exist when the decision was made.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .outcomes import expected_hit_rate
from .paper_signal import AdmissionPolicy, PaperSignalDecision, decide_paper_signal
from .regime_weights import RegimeRulebook, evaluate_blocks

SCHEMA_VERSION = "regime_replay_v1"


class ReplayError(ValueError):
    """Raised for malformed stored evidence, never for an empty window."""


@dataclass(frozen=True)
class ReplayCase:
    """One recorded decision, reduced to what a replay needs.

    ``outcome_signed_return_pct`` and ``market_move_pct`` come from the measured
    outcome and are used only to score the replay, never as an input to it.
    """

    signal_id: str
    symbol: str
    evaluated_at_ms: int
    block_scores: dict[str, float]
    block_qualities: dict[str, float]
    directional: dict[str, Any]
    outcome_signed_return_pct: float | None = None
    market_move_pct: float | None = None


def case_from_stored_evidence(
    signal_id: str,
    symbol: str,
    stored: Mapping[str, Any],
    outcome_signed_return_pct: float | None = None,
    market_move_pct: float | None = None,
) -> ReplayCase:
    """Build a replay case from a persisted ``paper_signal_v1`` payload."""

    evidence = stored.get("evidence")
    if not isinstance(evidence, Mapping):
        raise ReplayError(f"signal {signal_id} has no evidence block")
    contributions = evidence.get("contributions")
    if not isinstance(contributions, Mapping) or not contributions:
        raise ReplayError(f"signal {signal_id} recorded no block contributions")

    block_scores: dict[str, float] = {}
    block_qualities: dict[str, float] = {}
    for block, detail in contributions.items():
        if not isinstance(detail, Mapping):
            continue
        quality = detail.get("quality")
        score = detail.get("score")
        if not isinstance(quality, (int, float)) or not isinstance(score, (int, float)):
            continue
        # A block with zero quality contributed nothing and must not be
        # resurrected by a challenger that happens to weight it heavily.
        if float(quality) <= 0:
            continue
        block_scores[block] = float(score)
        block_qualities[block] = float(quality)

    return ReplayCase(
        signal_id=signal_id,
        symbol=symbol,
        evaluated_at_ms=int(evidence.get("evaluated_at_ms") or 0),
        block_scores=block_scores,
        block_qualities=block_qualities,
        directional=dict(evidence.get("directional") or {}),
        outcome_signed_return_pct=outcome_signed_return_pct,
        market_move_pct=market_move_pct,
    )


def replay_case(
    case: ReplayCase,
    rulebook: RegimeRulebook,
    policy: AdmissionPolicy,
    catalog_summary: Mapping[str, Any],
) -> PaperSignalDecision:
    """Decide what this rulebook would have concluded from the same evidence."""

    evaluation = evaluate_blocks(
        rulebook, case.block_scores, case.block_qualities, []
    )
    return decide_paper_signal(
        symbol=case.symbol,
        evaluation=evaluation,
        # The per-feature admission checks already passed when this evidence was
        # recorded. Replaying them against a later clock would reject every case
        # as stale, which would measure the age of the sample, not the rulebook.
        feature_results=_synthetic_feature_results(case),
        catalog_summary=catalog_summary,
        evaluated_at_ms=case.evaluated_at_ms,
        policy=policy,
        directional=case.directional or None,
    )


def _synthetic_feature_results(case: ReplayCase) -> list[dict[str, Any]]:
    """Represent the recorded contributors as admitted feature results.

    Provenance is ``derived`` and the observation time is the original
    evaluation time, so freshness and provenance gates behave exactly as they
    did when the decision was first taken.
    """

    contributors = case.directional.get("contributors") or []
    results: list[dict[str, Any]] = []
    for item in contributors:
        if not isinstance(item, Mapping):
            continue
        results.append(
            {
                "feature_id": item.get("feature_id"),
                "block": "price_volatility",
                "provenance": "derived",
                "observed_at_ms": case.evaluated_at_ms,
                "scoring_allowed": True,
                "score": item.get("score"),
                "data_quality": item.get("quality"),
            }
        )
    if not results:
        # No directional contributor recorded: represent the suitability
        # evidence so the decision still sees admitted features and refuses for
        # the right reason rather than for having no evidence at all.
        for block, quality in case.block_qualities.items():
            results.append(
                {
                    "feature_id": f"recorded:{block}",
                    "block": block,
                    "provenance": "derived",
                    "observed_at_ms": case.evaluated_at_ms,
                    "scoring_allowed": True,
                    "score": case.block_scores.get(block, 0.0),
                    "data_quality": quality,
                }
            )
    return results


def score_replay(
    cases: Sequence[ReplayCase],
    decisions: Sequence[PaperSignalDecision],
) -> dict[str, Any]:
    """Score one rulebook's replayed decisions against measured outcomes."""

    if len(cases) != len(decisions):
        raise ReplayError("cases and decisions must correspond one to one")

    admitted = [
        (case, decision)
        for case, decision in zip(cases, decisions)
        if decision.admitted
        and case.outcome_signed_return_pct is not None
        and case.market_move_pct is not None
    ]
    if not admitted:
        return {
            "admitted": 0,
            "measured": 0,
            "hit_rate": None,
            "expected_hit_rate": None,
            "skill_vs_baseline": None,
            "mean_signed_return_pct": None,
            "note": "no admitted decision in this window has a measured outcome",
        }

    # The stored outcome is signed for the direction that was originally taken.
    # If the replay chose the other side, the sign flips with it.
    signed: list[float] = []
    longs = 0
    ups = 0
    for case, decision in admitted:
        move = case.market_move_pct or 0.0
        sign = 1.0 if decision.direction == "LONG" else -1.0
        signed.append(move * sign)
        longs += 1 if decision.direction == "LONG" else 0
        ups += 1 if move > 0 else 0

    total = len(signed)
    wins = sum(1 for value in signed if value > 0)
    hit_rate = wins / total
    up_rate = ups / total
    long_share = longs / total
    baseline = expected_hit_rate(up_rate, long_share)

    return {
        "admitted": total,
        "measured": total,
        "hit_rate": round(hit_rate, 6),
        "market_up_rate": round(up_rate, 6),
        "long_share": round(long_share, 6),
        "expected_hit_rate": round(baseline, 6),
        "skill_vs_baseline": round(hit_rate - baseline, 6),
        "mean_signed_return_pct": round(sum(signed) / total, 6),
        "note": (
            "Scored on the same frozen evidence window as every other rulebook "
            "in this comparison. Skill is hit_rate minus what this direction "
            "mix would score by luck."
        ),
    }


def compare_rulebooks(
    cases: Sequence[ReplayCase],
    champion: RegimeRulebook,
    challenger: RegimeRulebook,
    policy: AdmissionPolicy,
    catalog_summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Run both rulebooks over one frozen window and report the difference."""

    champion_decisions = [
        replay_case(case, champion, policy, catalog_summary) for case in cases
    ]
    challenger_decisions = [
        replay_case(case, challenger, policy, catalog_summary) for case in cases
    ]

    champion_score = score_replay(cases, champion_decisions)
    challenger_score = score_replay(cases, challenger_decisions)

    changed = [
        {
            "signal_id": case.signal_id,
            "symbol": case.symbol,
            "champion": champ.direction if champ.admitted else "NONE",
            "challenger": chall.direction if chall.admitted else "NONE",
        }
        for case, champ, chall in zip(cases, champion_decisions, challenger_decisions)
        if (champ.admitted, champ.direction) != (chall.admitted, chall.direction)
    ]

    def _delta(key: str) -> float | None:
        a, b = challenger_score.get(key), champion_score.get(key)
        return None if a is None or b is None else round(a - b, 6)

    return {
        "schema_version": SCHEMA_VERSION,
        "window_cases": len(cases),
        "champion": {
            "rulebook_id": champion.rulebook_id,
            "version": champion.version,
            "digest": champion.digest,
            "weights": champion.weights,
            "result": champion_score,
        },
        "challenger": {
            "rulebook_id": challenger.rulebook_id,
            "version": challenger.version,
            "digest": challenger.digest,
            "weights": challenger.weights,
            "result": challenger_score,
        },
        "delta": {
            "hit_rate": _delta("hit_rate"),
            "skill_vs_baseline": _delta("skill_vs_baseline"),
            "mean_signed_return_pct": _delta("mean_signed_return_pct"),
            "admitted": _delta("admitted"),
        },
        "changed_decisions": changed,
        "note": (
            "Both rulebooks saw identical recorded evidence, so any difference "
            "is attributable to the configuration. A single-regime window still "
            "cannot establish that a challenger is better in general."
        ),
    }
