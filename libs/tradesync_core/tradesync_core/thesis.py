"""Assemble the SOP's minimum valid thesis from measured evidence.

The Daily Thesis SOP names seven parts: chart structure, anchor levels, a
confirmation stack, invalidation, no-trade conditions, confidence, and the
public/private separation. This module builds exactly that object from what
the system has *measured* — the entry-time regime, venue candles, the scoring
contributors with what each has earned, the skill gate, the economic calendar
and the execution gate. Nothing here is drafted by a model and nothing here
sets a direction of its own: the direction is the paper signal's, and the
confidence is evidence coverage, never a win probability.

Every line carries where it came from and how old it was, because the SOP's
freshness gates refuse a stale thesis rather than render one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .thesis_context import derivatives_line, derivatives_read

SCHEMA_VERSION = "thesis_v1"
VISIBILITY = "private"  # never published; the SOP separates public and private
STALE_AFTER_MS = 120_000
HIGH_IMPACT_WINDOW_MINUTES = 120
LOW_COVERAGE_BELOW = 0.5


@dataclass(frozen=True)
class Line:
    """One rendered sentence with its provenance."""

    text: str
    source: str
    captured_at_ms: int | None = None
    age_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "source": self.source, "captured_at_ms": self.captured_at_ms, "age_ms": self.age_ms}


@dataclass
class NoTradeCondition:
    code: str
    active: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "active": self.active, "detail": self.detail}


def anchor_levels(candles: Sequence[Mapping[str, Any]], bucket_s: int) -> dict[str, Any]:
    """24h, 4h and 1h highs and lows from closed candles, newest last.

    ``candles`` are venue OHLCV rows ``{time, open, high, low, close}`` with
    ``time`` as the bucket open in seconds. Missing coverage is reported, not
    padded: a 24h high from six hours of candles is not a 24h high.
    """
    rows = sorted((c for c in candles if _finite(c.get("high")) and _finite(c.get("low"))), key=lambda c: c["time"])
    out: dict[str, Any] = {"source": "hyperliquid candles", "bucket_s": bucket_s, "candles": len(rows)}
    if not rows:
        out["note"] = "no candles; anchors unavailable"
        return out
    last = rows[-1]
    out["last_close"] = float(last["close"]) if _finite(last.get("close")) else None
    out["last_open"] = float(last["open"]) if _finite(last.get("open")) else None
    for label, hours in (("1h", 1), ("4h", 4), ("24h", 24)):
        need = max(1, hours * 3600 // bucket_s)
        window = rows[-need:]
        out[f"high_{label}"] = max(float(c["high"]) for c in window)
        out[f"low_{label}"] = min(float(c["low"]) for c in window)
        out[f"covered_{label}"] = len(window) >= need
    return out


def invalidation(direction: str, anchors: Mapping[str, Any], regime: str) -> dict[str, Any]:
    """The level that would falsify the read, and the rule that says so.

    A SHORT read in a falling hour is wrong once price reclaims the hour's
    high; a LONG read is wrong once it loses the hour's low. With no
    direction there is nothing to invalidate.
    """
    if direction not in ("LONG", "SHORT"):
        return {"level": None, "rule": "no directional read; nothing to invalidate"}
    key = "high_1h" if direction == "SHORT" else "low_1h"
    level = anchors.get(key)
    verb = "reclaims" if direction == "SHORT" else "loses"
    return {
        "level": level,
        "rule": f"{direction} read is invalid once price {verb} the trailing 1h {'high' if direction == 'SHORT' else 'low'}"
        + (f" ({regime} entry regime)" if regime and regime != "unknown" else ""),
        "source": anchors.get("source"),
    }


def confirmation_stack(
    contributors: Sequence[Mapping[str, Any]],
    cards_by_feature: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Each scoring contributor with what the evidence cards say it has earned."""
    stack = []
    for c in contributors:
        fid = str(c.get("feature_id"))
        card = cards_by_feature.get(fid, {})
        score = c.get("score")
        stack.append(
            {
                "feature_id": fid,
                "score": score,
                "reads": "LONG" if isinstance(score, (int, float)) and score > 0 else "SHORT" if isinstance(score, (int, float)) and score < 0 else "flat",
                "quality": c.get("quality"),
                "standing": card.get("standing", "unknown"),
                "earned": bool(card.get("earned", False)),
                "earned_by": list(card.get("earned_by", [])),
                "entries_with_reading": card.get("entries_with_reading"),
            }
        )
    return stack


def no_trade_conditions(
    *,
    gate: str | None,
    execution_enabled: bool,
    observation_age_ms: int | None,
    source_live: bool,
    coverage: float | None,
    events: Sequence[Mapping[str, Any]],
    earned_count: int,
) -> list[NoTradeCondition]:
    """Every reason not to trade, each stated whether or not it is active."""
    soon = [
        e for e in events
        if e.get("impact") == "High" and isinstance(e.get("minutes_until"), int)
        and 0 <= e["minutes_until"] <= HIGH_IMPACT_WINDOW_MINUTES
    ]
    stale = observation_age_ms is None or observation_age_ms > STALE_AFTER_MS or not source_live
    return [
        NoTradeCondition("no_demonstrated_edge", gate != "OPEN",
                         "skill gate is CLOSED: no cell shows economic edge after costs" if gate != "OPEN" else "skill gate reports economic edge in at least one cell"),
        NoTradeCondition("no_earned_inputs", earned_count == 0,
                         "no scoring input has earned its weight on the evidence cards" if earned_count == 0 else f"{earned_count} input(s) have earned a weight"),
        NoTradeCondition("execution_disabled", not execution_enabled,
                         "EXECUTION_ENABLED is false: paper only" if not execution_enabled else "execution gate open"),
        NoTradeCondition("stale_evidence", stale,
                         "market observations are stale or the source is not live" if stale else "observations current"),
        NoTradeCondition("low_coverage", coverage is None or coverage < LOW_COVERAGE_BELOW,
                         f"evidence coverage {coverage if coverage is not None else 'unknown'} below {LOW_COVERAGE_BELOW}" if coverage is None or coverage < LOW_COVERAGE_BELOW else f"evidence coverage {coverage:.2f}"),
        NoTradeCondition("high_impact_event_near", bool(soon),
                         ("; ".join(f"{e.get('title')} in {e.get('minutes_until')} min" for e in soon[:3])) if soon else f"no High-impact event within {HIGH_IMPACT_WINDOW_MINUTES} min"),
    ]


def build_thesis(
    *,
    symbol: str,
    now_ms: int,
    regime: Mapping[str, Any] | None,
    signal: Mapping[str, Any] | None,
    source_status: Mapping[str, Any],
    observation_age_ms: int | None,
    candles: Sequence[Mapping[str, Any]],
    bucket_s: int,
    contributors: Sequence[Mapping[str, Any]],
    cards: Sequence[Mapping[str, Any]],
    gate: Mapping[str, Any] | None,
    events: Sequence[Mapping[str, Any]],
    execution_enabled: bool,
    feature_results: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """The minimum valid thesis, as data plus rendered lines."""
    derivatives = derivatives_read(feature_results, now_ms)
    newest_context = max((d["observed_at_ms"] for d in derivatives if d["observed_at_ms"]), default=None)
    direction = str((signal or {}).get("direction") or "NONE")
    coverage = _float((signal or {}).get("data_coverage"))
    directional_score = _float((signal or {}).get("directional_score"))
    signal_at_ms = (signal or {}).get("evaluated_at_ms")
    regime_label = str((regime or {}).get("regime") or "unknown")
    anchors = anchor_levels(candles, bucket_s)
    cards_by = {str(c.get("feature_id")): c for c in cards}
    stack = confirmation_stack(contributors, cards_by)
    earned = sum(1 for s in stack if s["earned"])
    gate_state = (gate or {}).get("gate")
    source_live = source_status.get("status") == "live"
    conditions = no_trade_conditions(
        gate=gate_state, execution_enabled=execution_enabled, observation_age_ms=observation_age_ms,
        source_live=source_live, coverage=coverage, events=events, earned_count=earned,
    )
    inval = invalidation(direction, anchors, regime_label)
    active = [c for c in conditions if c.active]
    verdict = "NO TRADE" if active else "PAPER READ ONLY"

    lines = [
        Line(
            f"{symbol}: the last hour before the latest paper signal was {regime_label}"
            + (f" ({regime['trailing_return_pct']:+.2f}% trailing)" if _finite((regime or {}).get('trailing_return_pct')) else "")
            + ".",
            "opportunity_entry_regimes (candles closed before entry)",
            _int((regime or {}).get("computed_at_ms")),
            _age(now_ms, (regime or {}).get("computed_at_ms")),
        ),
        Line(
            (f"Paper read is {direction} with directional score {directional_score:+.2f} and evidence coverage {coverage:.2f}"
             + (f" ({signal['read_source']})." if (signal or {}).get("read_source") else ".")
             if direction in ("LONG", "SHORT") and directional_score is not None and coverage is not None
             else "No admitted paper read for this symbol right now."),
            "core-scorer paper signal (regime rulebook)", _int(signal_at_ms), _age(now_ms, signal_at_ms),
        ),
        Line(
            (f"Anchors: 24h {anchors.get('low_24h'):,.2f}–{anchors.get('high_24h'):,.2f}, 4h {anchors.get('low_4h'):,.2f}–{anchors.get('high_4h'):,.2f}, "
             f"1h {anchors.get('low_1h'):,.2f}–{anchors.get('high_1h'):,.2f}, last close {anchors.get('last_close'):,.2f}."
             if anchors.get("high_24h") is not None else "Anchors unavailable: no candles."),
            f"{anchors.get('source')} {bucket_s}s buckets",
            None, None,
        ),
        Line(
            derivatives_line(derivatives),
            "catalog feature results (current values, context-only ones score nothing)",
            newest_context, _age(now_ms, newest_context),
        ),
        Line(
            ("Confirmation stack: " + "; ".join(
                f"{s['feature_id']} reads {s['reads']} ({s['score']:+.2f}), {s['standing'].replace('_', ' ')}, "
                + ("earned " + ", ".join(s["earned_by"]) if s["earned"] else "weight not yet earned")
                for s in stack
            ) + ".") if stack else "Confirmation stack: no scoring contributors ready.",
            "regime evaluation contributors + evidence cards", _int(signal_at_ms), _age(now_ms, signal_at_ms),
        ),
        Line(
            (f"Invalidation: {inval['rule']} at {inval['level']:,.2f}." if inval.get("level") is not None else f"Invalidation: {inval['rule']}."),
            "anchor levels", None, None,
        ),
        Line(
            "No-trade conditions active: " + ("; ".join(f"{c.code} ({c.detail})" for c in active) if active else "none") + ".",
            "skill gate, evidence cards, execution status, market liveness, economic calendar", now_ms, 0,
        ),
        Line(
            f"Confidence is evidence coverage {coverage:.2f} — the share of the rulebook's weight with admissible evidence, not a win probability."
            if coverage is not None else "Confidence: no coverage figure without an admitted read.",
            "core-scorer data_coverage", _int(signal_at_ms), _age(now_ms, signal_at_ms),
        ),
        Line(f"Verdict: {verdict}. Private thesis; not for publication.", "thesis assembler", now_ms, 0),
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "symbol": symbol,
        "generated_at_ms": now_ms,
        "visibility": VISIBILITY,
        "verdict": verdict,
        "freshness": {
            "source_status": dict(source_status),
            "observation_age_ms": observation_age_ms,
            "stale": observation_age_ms is None or observation_age_ms > STALE_AFTER_MS or not source_live,
            "stale_after_ms": STALE_AFTER_MS,
        },
        "structure": {
            "entry_regime": regime_label,
            "trailing_return_pct": _float((regime or {}).get("trailing_return_pct")),
            "lookback_minutes": (regime or {}).get("lookback_minutes"),
            "direction": direction,
            "directional_score": directional_score,
            "signal_evaluated_at_ms": _int(signal_at_ms),
        },
        "anchors": anchors,
        "derivatives": derivatives,
        "confirmation_stack": stack,
        "invalidation": inval,
        "no_trade_conditions": [c.to_dict() for c in conditions],
        "confidence": {
            "evidence_coverage": coverage,
            "meaning": "share of rulebook weight with admissible evidence; never a win probability",
        },
        "skill_gate": {"gate": gate_state, "any_economic_edge": bool((gate or {}).get("any_economic_edge", False))},
        "upcoming_events": [dict(e) for e in events[:5]],
        "lines": [line.to_dict() for line in lines],
        "text": "\n".join(line.text for line in lines),
        "note": (
            "Assembled from measured evidence only. Direction is the paper signal's; "
            "confidence is coverage; every line names its source and age. "
            "No model drafted this and nothing here can act."
        ),
    }


def _finite(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")


def _float(v: Any) -> float | None:
    return float(v) if _finite(v) else None


def _int(v: Any) -> int | None:
    return int(v) if _finite(v) else None


def _age(now_ms: int, at_ms: Any) -> int | None:
    return now_ms - int(at_ms) if _finite(at_ms) else None
