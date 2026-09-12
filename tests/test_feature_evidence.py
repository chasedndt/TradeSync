"""A feature's sign is scored as a call; both polarities are paid for together."""

from __future__ import annotations

from tradesync_core.edge_evidence import CostAssumptions
from tradesync_core.feature_evidence import (
    FeatureOutcomeRow,
    as_guesser,
    assess_feature_cards,
    catalog_standing,
    group_cells,
)

COSTS = CostAssumptions(0.09, 0.02, 0.01, source="test fixture, not a venue schedule")
HOUR = 3600


def row(feature: str, i: int, value: float, fwd: float, horizon: int = 60, symbol: str = "BTC-PERP"):
    return FeatureOutcomeRow(feature, symbol, i * 5 * HOUR, horizon, fwd, value)


def test_positive_reads_long_negative_reads_short_zero_abstains() -> None:
    assert as_guesser(row("f", 0, 2.0, 0.5), 1).direction == "LONG"
    assert as_guesser(row("f", 0, -2.0, 0.5), 1).direction == "SHORT"
    assert as_guesser(row("f", 0, 0.0, 0.5), 1) is None
    inverted = as_guesser(row("f", 0, 2.0, 0.5), -1)
    assert inverted.direction == "SHORT" and inverted.signed_return_pct == -0.5


def test_cells_are_keyed_by_feature_horizon_and_polarity() -> None:
    cells = group_cells([row("a", 0, 1.0, 0.1), row("a", 1, -1.0, 0.1, horizon=15), row("b", 2, 0.0, 0.1)])
    assert set(cells) == {("a", 60, "as_read"), ("a", 60, "inverted"), ("a", 15, "as_read"), ("a", 15, "inverted")}


def _rows(feature: str, right_share: float, n: int = 160, contrarian: bool = False):
    """Alternating sign; the market follows the sign ``right_share`` of the time."""
    out = []
    for i in range(n):
        value = 1.0 if i % 2 else -1.0
        agrees = (i % 10) < int(right_share * 10)
        fwd = 0.2 if (value > 0) == agrees else -0.2
        if contrarian:
            fwd = -fwd
        out.append(row(feature, i, value, fwd))
    return out


def test_a_feature_that_calls_direction_earns_in_its_read_polarity() -> None:
    cards, cells = assess_feature_cards(_rows("news", 0.80), ["news"], costs=COSTS, draws=100)
    card = cards[0]
    assert cells == 2 and card.feature_id == "news"
    assert card.earned and card.earned_by == ["60m as_read"]
    inverted = next(c for c in card.cells if c["polarity"] == "inverted")
    assert not inverted["earned"] and inverted["skill"] < 0


def test_a_contrarian_feature_earns_only_inverted() -> None:
    cards, _ = assess_feature_cards(_rows("funding", 0.80, contrarian=True), ["funding"], costs=COSTS, draws=100)
    assert cards[0].earned_by == ["60m inverted"]


def test_a_coin_flip_feature_earns_nothing_and_abstentions_are_counted() -> None:
    rows = _rows("noise", 0.50) + [row("noise", 500, 0.0, 0.1), row("noise", 501, 0.0, 0.1)]
    cards, _ = assess_feature_cards(rows, ["noise"], costs=COSTS, draws=100)
    assert not cards[0].earned and cards[0].abstained == 2


def test_every_listed_feature_gets_a_card_even_with_no_rows_and_order_is_the_catalogs() -> None:
    cards, cells = assess_feature_cards([], ["a", "b"], costs=COSTS, draws=10)
    assert [c.feature_id for c in cards] == ["a", "b"] and cells == 0
    assert all(not c.earned and c.cells == [] for c in cards)


def test_standing_reads_the_catalog_flag() -> None:
    assert catalog_standing({"scoring_eligible": True}) == "scoring"
    assert catalog_standing({"scoring_eligible": False}) == "context_only"
