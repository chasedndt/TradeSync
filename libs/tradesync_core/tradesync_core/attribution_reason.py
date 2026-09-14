"""The plain-English sentence that explains one measured paper call.

The sentence has three parts: what the price did after costs, which recorded
readings led or supported the call (named by their share of the decision,
largest first), and the regime at entry. It is written for a trader scanning a
list of failures, so every number carries its unit and every reading its
direction.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .decision_contributions import DIRECTIONAL
from .outcome_classification import (
    CLEAN_WIN,
    REVERSED,
    WIN_AFTER_DRAWDOWN,
    WRONG_DIRECTION,
    OutcomeClass,
)

FEATURE_LABELS = {
    "hl_return_1h_pct": "1h return",
    "hl_direct_cvd": "CVD order flow",
    "coinbase_premium_bps": "Coinbase premium",
    "hl_spread_bps": "spread",
    "hl_depth_25bp_usd": "depth within 25 bp",
    "hl_buy_impact_5k_bps": "$5k buy impact",
    "hl_orderbook_imbalance_1pct": "book imbalance",
}
BLOCK_LABELS = {
    "price_volatility": "price and volatility",
    "liquidity": "liquidity",
    "positioning": "positioning",
    "spot_premium": "spot premium",
    "macro_flows": "macro flows",
}
MAX_NAMED = 3


def label_for(key: str) -> str:
    return FEATURE_LABELS.get(key) or BLOCK_LABELS.get(key) or key.replace("_", " ")


def _pull(item: Mapping[str, Any]) -> str:
    positive = float(item.get("contribution") or 0.0) > 0
    if item.get("role") == DIRECTIONAL:
        return "pointed up" if positive else "pointed down"
    return "read conditions as favourable" if positive else "read conditions as unfavourable"


def _names(items: Sequence[Mapping[str, Any]]) -> str:
    named = [f"{item.get('label') or label_for(str(item.get('id')))} ({_pull(item)})" for item in items[:MAX_NAMED]]
    if len(items) > MAX_NAMED:
        named.append(f"{len(items) - MAX_NAMED} more")
    if len(named) <= 1:
        return "".join(named)
    return ", ".join(named[:-1]) + " and " + named[-1]


def _by_size(items: Sequence[Mapping[str, Any]], verdict: str | None = None, stance: str | None = None):
    chosen = [
        item for item in items
        if (verdict is None or item.get("verdict") == verdict)
        and (stance is None or item.get("stance") == stance)
    ]
    return sorted(chosen, key=lambda item: (-abs(float(item.get("contribution") or 0.0)), str(item.get("id"))))


def _headline(symbol: str, direction: str, horizon: int, o: OutcomeClass) -> str:
    side = f"{symbol.replace('-PERP', '')} {direction}"
    after = f"{o.net_return_pct:+.2f}% after {o.cost_pct:.2f}% costs"
    if o.classification == CLEAN_WIN:
        return (f"{side} made {o.signed_return_pct:+.2f}% over {horizon}m ({after}) "
                f"with a worst drawdown of {o.max_adverse_pct:.2f}%.")
    if o.classification == WIN_AFTER_DRAWDOWN:
        return (f"{side} finished {o.signed_return_pct:+.2f}% over {horizon}m ({after}), "
                f"but only after a {o.max_adverse_pct:.2f}% drawdown, deeper than the win.")
    if o.classification == REVERSED:
        return (f"{side} was {o.max_favourable_pct:.2f}% in favour, then reversed to "
                f"{o.signed_return_pct:+.2f}% over {horizon}m ({after}).")
    if o.classification == WRONG_DIRECTION:
        return (f"{side} went the wrong way: {o.signed_return_pct:+.2f}% over {horizon}m ({after}), "
                f"never more than {o.max_favourable_pct:.2f}% in favour.")
    return (f"{side} moved {o.signed_return_pct:+.2f}% over {horizon}m, inside the "
            f"{o.cost_pct:.2f}% round-trip costs ({o.net_return_pct:+.2f}% after costs).")


def _readings(direction: str, o: OutcomeClass, features: Sequence[Mapping[str, Any]]) -> str:
    if not features:
        return "No feature evidence was stored with this decision."
    if o.won:
        supported, misled = _by_size(features, "supported"), _by_size(features, "misled")
        text = f"Supported by {_names(supported)}." if supported else "No recorded reading pointed with the move."
        if misled:
            text += f" {_names(misled)} disagreed and {'was' if len(misled) == 1 else 'were'} outweighed."
        return text
    if o.decided:
        misled = _by_size(features, "misled")
        price = "fell" if direction == "LONG" else "rose"
        if not misled:
            return f"No recorded reading pointed with the call while price {price}."
        return f"Misled by {_names(misled)} while price {price}."
    pushed = _by_size(features, stance="with")
    if not pushed:
        return "No recorded reading pointed with the call."
    return f"{_names(pushed)} backed the call, but the move did not cover costs."


def reason_sentence(
    symbol: str,
    direction: str,
    horizon_minutes: int,
    outcome: OutcomeClass,
    features: Sequence[Mapping[str, Any]],
    entry_regime: str,
) -> str:
    """Headline, the readings that led or supported the call, and the entry regime."""

    regime = (entry_regime or "unknown").strip() or "unknown"
    tail = "Entry regime unknown." if regime == "unknown" else f"Entry regime: {regime}."
    readings = _readings(direction, outcome, features)
    return " ".join(
        [
            _headline(symbol, direction, horizon_minutes, outcome),
            readings[:1].upper() + readings[1:],
            tail,
        ]
    )
