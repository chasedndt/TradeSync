"""StrikeZone ledger lines become storable rows, and every trade call gets a status."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tradesync_core.strikezone_ledger import ledger_status, normalize_outcome, normalize_signal, num, planned_reward_risk

NOW = datetime(2026, 9, 13, 15, 0, tzinfo=timezone.utc)
SIGNAL = {
    "signal_id": "sig_1", "asset": "btc", "timeframe": "15m", "direction": "SHORT",
    "signal_at_utc": "2026-09-13T07:00:00Z", "candle_close_utc": "2026-09-13T07:00:00Z", "expiry_utc": "2026-09-13T11:00:00Z",
    "entry_reference_price": "101.19", "invalidation_price": "102.00", "target_price": "99.57", "confidence": "0.61",
    "regime": {"1h": "down"}, "methodology_version": "v1_3", "strategy_id": "ema-9-21-cross-atr",
}


def test_num_reads_decimal_strings_and_refuses_the_rest() -> None:
    assert num("101.19") == 101.19 and num(3) == 3.0
    for bad in ("", None, True, "nan", "inf", "x"):
        assert num(bad) is None


def test_a_trade_call_keeps_its_levels() -> None:
    row = normalize_signal(SIGNAL)
    assert row["asset"] == "BTC" and row["direction"] == "short"
    assert (row["entry_price"], row["invalidation_price"], row["target_price"]) == (101.19, 102.0, 99.57)
    assert row["signal_at"] == datetime(2026, 9, 13, 7, tzinfo=timezone.utc) and row["regime"] == {"1h": "down"}


def test_a_no_trade_call_has_no_levels_and_malformed_lines_are_refused() -> None:
    row = normalize_signal({**SIGNAL, "direction": "no_trade", "entry_reference_price": "5"})
    assert row["entry_price"] is None and row["confidence"] == 0.61
    assert normalize_signal({**SIGNAL, "direction": "flat"}) is None
    assert normalize_signal({**SIGNAL, "signal_id": ""}) is None
    assert normalize_signal({k: v for k, v in SIGNAL.items() if k not in ("signal_at_utc", "candle_close_utc")}) is None


def test_an_outcome_sums_its_fees_and_reads_funding_coverage() -> None:
    raw = {
        "outcome_id": "pout_1", "signal_id": "sig_1", "asset": "SOL", "timeframe": "1h", "direction": "short",
        "exit_reason": "target", "exit_at_utc": "2026-09-13T09:00:00Z", "entry_fee_usdc": "0.44991",
        "exit_fee_usdc": "0.44755", "net_pnl_usdc": "4.348", "gross_pnl_usdc": "5.2447",
        "funding_coverage": {"status": "complete"}, "holding_duration_minutes": "120",
    }
    row = normalize_outcome(raw)
    assert abs(row["fees_usdc"] - 0.89746) < 1e-9 and row["funding_coverage"] == "complete" and row["holding_minutes"] == 120.0
    assert normalize_outcome({**raw, "signal_id": None}) is None


def test_the_status_of_a_call() -> None:
    assert ledger_status("no_trade", None, False, NOW) == "no_trade"
    assert ledger_status("long", NOW - timedelta(minutes=30), True, NOW) == "resolved"
    assert ledger_status("long", NOW + timedelta(hours=1), False, NOW) == "open"
    assert ledger_status("short", NOW - timedelta(minutes=30), False, NOW) == "resolving"
    assert ledger_status("short", NOW - timedelta(hours=2), False, NOW) == "overdue"


def test_planned_reward_risk() -> None:
    assert planned_reward_risk(100.0, 99.0, 102.0) == 2.0
    assert planned_reward_risk(100.0, 100.0, 102.0) is None and planned_reward_risk(None, 1.0, 2.0) is None
