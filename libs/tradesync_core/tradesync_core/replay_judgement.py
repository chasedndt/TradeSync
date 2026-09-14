"""Judge a challenger rulebook by replaying one window of stored decisions.

Weights decide admission, not direction: since the direction/suitability split
the side comes only from directional evidence, which no weight touches. A
challenger therefore shows up mainly as admissions gained or lost. Both
rulebooks decide every recorded case with the live decision code
(``replay.replay_case``), and the judgement reports counts:

- over the replayed decisions: how many changed, admissions gained, admissions
  lost and direction flips;
- over the decisions with a measured outcome: each rulebook's admitted set, its
  hit rate, what its long/short mix would score by luck, the skill between the
  two and its mean signed return, each with its sample count.

Outcomes exist only for decisions that opened a paper opportunity, so an
admission a challenger gains on a decision the baseline refused usually has no
outcome. That shows as a count, never as a guess.
"""

from __future__ import annotations

from typing import Any, Collection, Mapping, Sequence

from .paper_signal import AdmissionPolicy, PaperSignalDecision
from .regime_weights import RegimeRulebook
from .replay import ReplayCase, replay_case, score_replay

SCHEMA_VERSION = "regime_replay_judgement_v1"
EXAMPLE_LIMIT = 20


def classify_change(
    baseline: PaperSignalDecision, challenger: PaperSignalDecision
) -> str | None:
    """None when both rulebooks decided the same; otherwise how the decision changed."""

    if (baseline.admitted, baseline.direction) == (challenger.admitted, challenger.direction):
        return None
    if challenger.admitted and not baseline.admitted:
        return "admissions_gained"
    if baseline.admitted and not challenger.admitted:
        return "admissions_lost"
    return "direction_flips"


def _has_outcome(case: ReplayCase) -> bool:
    return case.outcome_signed_return_pct is not None and case.market_move_pct is not None


def _outcome_side(scored: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "admitted_with_outcome": scored["measured"],
        "hit_rate": scored["hit_rate"],
        "expected_hit_rate": scored["expected_hit_rate"],
        "skill": scored["skill_vs_baseline"],
        "mean_signed_return_pct": scored["mean_signed_return_pct"],
    }


def _delta(challenger: Mapping[str, Any], baseline: Mapping[str, Any], key: str) -> float | None:
    a, b = challenger.get(key), baseline.get(key)
    return None if a is None or b is None else round(a - b, 6)


def _rulebook_summary(rulebook: RegimeRulebook, admitted: int) -> dict[str, Any]:
    return {
        "rulebook_id": rulebook.rulebook_id,
        "version": rulebook.version,
        "digest": rulebook.digest,
        "weights": rulebook.weights,
        "admitted": admitted,
    }


def judge_window(
    cases: Sequence[ReplayCase],
    baseline: RegimeRulebook,
    challenger: RegimeRulebook,
    policy: AdmissionPolicy,
    catalog_summary: Mapping[str, Any],
    *,
    sampled_ids: Collection[str] | None = None,
    example_limit: int = EXAMPLE_LIMIT,
) -> dict[str, Any]:
    """Replay ``cases`` under both rulebooks and count what the challenger changed.

    ``sampled_ids`` limits the decision counts to a sample of the window (every
    case when ``None``); the outcome comparison always uses every case that has
    a measured outcome, because those are the scarce ones.
    """

    baseline_decisions = [replay_case(case, baseline, policy, catalog_summary) for case in cases]
    challenger_decisions = [replay_case(case, challenger, policy, catalog_summary) for case in cases]

    counts = {"replayed": 0, "changed": 0, "admissions_gained": 0, "admissions_lost": 0, "direction_flips": 0}
    admitted = {"baseline": 0, "challenger": 0}
    changed: list[dict[str, Any]] = []
    for case, base, chall in zip(cases, baseline_decisions, challenger_decisions):
        if sampled_ids is not None and case.signal_id not in sampled_ids:
            continue
        counts["replayed"] += 1
        admitted["baseline"] += int(base.admitted)
        admitted["challenger"] += int(chall.admitted)
        kind = classify_change(base, chall)
        if kind is None:
            continue
        counts["changed"] += 1
        counts[kind] += 1
        changed.append(
            {
                "signal_id": case.signal_id,
                "symbol": case.symbol,
                "evaluated_at_ms": case.evaluated_at_ms,
                "change": kind,
                "baseline": base.direction if base.admitted else "NONE",
                "challenger": chall.direction if chall.admitted else "NONE",
                "baseline_coverage": base.data_coverage,
                "challenger_coverage": chall.data_coverage,
                "has_outcome": _has_outcome(case),
            }
        )

    measured = [index for index, case in enumerate(cases) if _has_outcome(case)]
    outcome_cases = [cases[index] for index in measured]
    base_side = _outcome_side(score_replay(outcome_cases, [baseline_decisions[i] for i in measured]))
    chall_side = _outcome_side(score_replay(outcome_cases, [challenger_decisions[i] for i in measured]))

    return {
        "schema_version": SCHEMA_VERSION,
        "baseline": _rulebook_summary(baseline, admitted["baseline"]),
        "challenger": _rulebook_summary(challenger, admitted["challenger"]),
        "decisions": counts,
        "outcomes": {
            "cases_with_outcome": len(measured),
            "baseline": base_side,
            "challenger": chall_side,
            "delta": {
                key: _delta(chall_side, base_side, key)
                for key in ("hit_rate", "skill", "mean_signed_return_pct")
            },
        },
        "changed_examples": list(reversed(changed[-example_limit:])) if example_limit > 0 else [],
        "note": (
            "Both rulebooks decided the same recorded evidence with the live decision code. "
            "Weights change admission, not direction. Outcomes exist only for decisions that "
            "opened a paper opportunity, so admissions a challenger gains are mostly unmeasured. "
            "One window cannot show that a challenger is better in general."
        ),
    }
