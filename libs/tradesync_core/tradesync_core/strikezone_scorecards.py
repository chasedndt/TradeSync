"""The StrikeZone lab's scorecards and regime cohorts, with decimal strings made numbers.

The daily scorecard job writes one scorecard per asset and timeframe for the
active methodology, and a table of cohorts split by session, trend or range
regime, volatility and event proximity. Scores are withheld below the lab's
independent-sample, multi-day and multi-regime floors; that reason is kept.
"""

from __future__ import annotations

from typing import Any, Mapping

from tradesync_core.strikezone_ledger import num
from tradesync_core.strikezone_summary import ASSET_ORDER, TIMEFRAME_ORDER, _int, _rank

_NUMBERS = (
    "win_rate_percentage", "net_pnl_usdc", "expectancy_usdc_per_trade", "profit_factor", "maximum_drawdown_usdc",
    "total_fees_usdc", "total_slippage_usdc", "total_funding_cost_usdc", "average_holding_minutes",
    "gross_profit_usdc", "gross_loss_usdc", "strategy_score_percentage",
)
_COUNTS = (
    "resolved_trades", "wins", "losses", "breakevens", "correlation_adjusted_sample", "independent_day_count",
    "independent_regime_count", "minimum_sample", "minimum_independent_days", "minimum_independent_regimes",
)
_COHORT_LABELS = ("asset", "timeframe", "utc_session", "trend_range_regime", "volatility_bucket", "event_proximity", "sample_adequacy")


def _results(block: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(block, Mapping):
        return {}
    return {
        str(name): {"trades": _int(v.get("trades")), "wins": _int(v.get("wins")), "losses": _int(v.get("losses")),
                    "net_pnl_usdc": num(v.get("net_pnl_usdc"))}
        for name, v in block.items() if isinstance(v, Mapping)
    }


def scorecard_rows(doc: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for card in (doc or {}).get("scorecards") or []:
        if not isinstance(card, Mapping):
            continue
        calibration = card.get("confidence_calibration") if isinstance(card.get("confidence_calibration"), Mapping) else {}
        row: dict[str, Any] = {
            "asset": str(card.get("asset") or ""),
            "timeframe": str(card.get("timeframe") or ""),
            "maturity": str(card.get("maturity") or ""),
            "score_withheld_reason": card.get("score_withheld_reason"),
        }
        row.update({k: num(card.get(k)) for k in _NUMBERS})
        row.update({k: _int(card.get(k)) for k in _COUNTS})
        row["brier_score"] = num(calibration.get("brier_score"))
        row["average_confidence"] = num(calibration.get("average_confidence"))
        row["realized_win_rate"] = num(calibration.get("realized_win_rate"))
        row["rolling_7d"] = _results({"7d": card.get("rolling_7d")}).get("7d")
        row["direction_results"] = _results(card.get("direction_results"))
        row["session_results"] = _results(card.get("session_results"))
        row["regime_results"] = _results(card.get("regime_results"))
        exits = card.get("exit_reason_counts")
        row["exit_reason_counts"] = {str(k): _int(v) for k, v in exits.items()} if isinstance(exits, Mapping) else {}
        rows.append(row)
    rows.sort(key=lambda r: (_rank(r["asset"], ASSET_ORDER), _rank(r["timeframe"], TIMEFRAME_ORDER)))
    return rows


def _cohort(c: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {k: (str(c[k]) if c.get(k) is not None else None) for k in _COHORT_LABELS}
    out.update({k: _int(c.get(k)) for k in ("resolved_trades", "wins", "losses", "breakevens", "independent_sample", "minimum_independent_sample")})
    out.update({k: num(c.get(k)) for k in ("win_rate_percentage", "net_pnl_usdc", "expectancy_usdc_per_trade")})
    return out


def cohort_rows(doc: Mapping[str, Any] | None) -> dict[str, Any]:
    block = (doc or {}).get("regime_conditioned_paper_analytics")
    if not isinstance(block, Mapping):
        return {"cohorts": [], "aggregate": None, "dimensions": None, "minimum_independent_sample": None}
    cohorts = [_cohort(c) for c in block.get("cohorts") or [] if isinstance(c, Mapping)]
    cohorts.sort(key=lambda c: (-c["independent_sample"], _rank(c["asset"] or "", ASSET_ORDER), _rank(c["timeframe"] or "", TIMEFRAME_ORDER)))
    aggregate = block.get("aggregate")
    return {
        "cohorts": cohorts,
        "aggregate": _cohort(aggregate) if isinstance(aggregate, Mapping) else None,
        "dimensions": block.get("dimensions"),
        "minimum_independent_sample": _int(block.get("minimum_independent_sample")) or None,
    }


def assumption_view(doc: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not doc:
        return None
    return {
        "paper_notional_usdc": num(doc.get("paper_notional_usdc")),
        "entry_fee_rate": num(doc.get("entry_fee_rate")),
        "exit_fee_rate": num(doc.get("exit_fee_rate")),
        "adverse_slippage_bps_each_fill": num(doc.get("adverse_slippage_bps_each_fill")),
        "liquidity": f"{doc.get('entry_liquidity') or '?'} in, {doc.get('exit_liquidity') or '?'} out",
        "funding_cost_model": doc.get("funding_cost_model"),
        "minimum_scorecard_sample": _int(doc.get("minimum_scorecard_sample")) or None,
        "note": doc.get("note"),
    }
