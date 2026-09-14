"""A rehearsed fill states its costs and refuses to assume any it did not measure."""

from __future__ import annotations

import pytest

from tradesync_core.paper_rehearsal import HYPERLIQUID_BASE_FEES, RehearsalError, simulate_fill
from tradesync_core.risk import ReasonCode, RiskGuardian

T = 1_789_200_000_000


def test_a_long_crosses_half_the_spread_and_pays_the_taker_fee() -> None:
    fill = simulate_fill("LONG", 1_000.0, 100.0, spread_bps=2.0, observed_at_ms=T)
    assert fill["fill_price"] == pytest.approx(100.01)  # +1bp: half of 2bp
    assert fill["fee_usd"] == pytest.approx(0.45)  # 0.045% taker
    assert fill["slippage_usd"] == pytest.approx(0.1, rel=1e-3)
    assert fill["breakeven_move_pct"] == pytest.approx(0.055, rel=1e-2)
    assert fill["simulated"] is True
    assert fill["fees"]["source"].startswith("https://hyperliquid.gitbook.io")


def test_a_short_crosses_the_other_way() -> None:
    fill = simulate_fill("SHORT", 1_000.0, 100.0, spread_bps=2.0, observed_at_ms=T)
    assert fill["fill_price"] == pytest.approx(99.99)


def test_a_missing_spread_is_refused_not_assumed_free() -> None:
    with pytest.raises(RehearsalError, match="spread_bps is required"):
        simulate_fill("LONG", 100.0, 100.0, spread_bps=None, observed_at_ms=T)


def test_malformed_inputs_are_refused() -> None:
    with pytest.raises(RehearsalError):
        simulate_fill("NONE", 100.0, 100.0, 1.0, T)
    with pytest.raises(RehearsalError):
        simulate_fill("LONG", 0.0, 100.0, 1.0, T)
    with pytest.raises(RehearsalError):
        simulate_fill("LONG", 100.0, 0.0, 1.0, T)
    with pytest.raises(RehearsalError):
        simulate_fill("LONG", 100.0, 100.0, 1.0, 0)


def test_fee_schedule_names_its_source_and_date() -> None:
    assert HYPERLIQUID_BASE_FEES.taker_fee == 0.00045
    assert HYPERLIQUID_BASE_FEES.maker_fee == 0.00015
    assert HYPERLIQUID_BASE_FEES.read_on == "2026-09-14"


def test_rehearsal_skips_only_the_global_gate_and_keeps_every_symbol_rule(monkeypatch) -> None:
    """With the gate shut, preview refuses everything; rehearsal still applies DNT."""
    monkeypatch.setenv("EXECUTION_ENABLED", "false")
    guard = RiskGuardian()
    assert guard.execution_enabled is False

    opp = {"status": "new", "symbol": "BTC-PERP", "quality": 60.0}
    preview = guard.check("BTC-PERP", 100.0, opp, phase="preview")
    assert preview.reason_code == ReasonCode.EXEC_DISABLED

    rehearsal = guard.check("BTC-PERP", 100.0, opp, phase="rehearsal")
    assert rehearsal.reason_code != ReasonCode.EXEC_DISABLED

    blacklisted = guard.check("LUNA-PERP", 100.0, {**opp, "symbol": "LUNA-PERP"}, phase="rehearsal")
    assert blacklisted.reason_code == ReasonCode.DNT


def test_a_rehearsal_of_a_consumed_opportunity_is_a_duplicate(monkeypatch) -> None:
    monkeypatch.setenv("EXECUTION_ENABLED", "false")
    verdict = RiskGuardian().check("BTC-PERP", 100.0, {"status": "expired", "symbol": "BTC-PERP"}, phase="rehearsal")
    assert verdict.reason_code == ReasonCode.DUPLICATE
