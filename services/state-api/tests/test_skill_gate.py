"""The skill gate groups by entry regime and assesses every cell together."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.skill_gate import COSTS, rows_to_observations
from tradesync_core.edge_evidence import assess_cells

T0 = datetime(2026, 9, 12, tzinfo=timezone.utc)


def row(h, regime, minute, direction="LONG", fwd=0.1, symbol="BTC-PERP"):
    return {
        "horizon_minutes": h, "symbol": symbol, "direction": direction,
        "opened_at": T0 + timedelta(minutes=minute), "forward_return_pct": fwd,
        "signed_return_pct": fwd if direction == "LONG" else -fwd, "regime": regime,
    }


def test_rows_group_by_horizon_and_entry_regime_with_unknown_kept() -> None:
    cells = rows_to_observations([row(15, "rising", 0), row(15, "falling", 5), row(60, None, 10)])
    assert set(cells) == {(15, "rising"), (15, "falling"), (60, "unknown")}
    obs = cells[(15, "rising")][0]
    assert obs.opened_at_s == int(T0.timestamp()) and obs.hit is True


def test_costs_name_their_source_and_use_the_published_fee() -> None:
    assert abs(COSTS.round_trip_fee_pct - 0.09) < 1e-9  # 2 x 0.045%
    assert "hyperliquid.gitbook.io" in COSTS.source
    assert COSTS.total_pct > COSTS.round_trip_fee_pct


def test_cells_are_holm_adjusted_together_not_one_at_a_time() -> None:
    """One marginal cell among several nulls does not become 'positive skill'."""
    def cell(label, seed_bias):
        return [row(15, label, i * 300, "LONG" if i % 2 else "SHORT",
                    (0.1 if i % 2 else -0.1) if (i % 10) < seed_bias else (-0.1 if i % 2 else 0.1))
                for i in range(120)]
    rows = cell("a", 6) + cell("b", 5) + cell("c", 5) + cell("d", 5) + cell("e", 5) + cell("f", 5)
    cells = rows_to_observations(rows)
    assessed = assess_cells([(k[1], k[0], v) for k, v in sorted(cells.items())], costs=COSTS, draws=100)
    assert not any(c.positive_skill for c in assessed)
