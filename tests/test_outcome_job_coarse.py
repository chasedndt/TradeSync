"""When the venue has only 5m history left, say so; measure only what 5m can carry."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _service_import import load_service_module  # noqa: E402

from tradesync_core.outcomes import HorizonOutcome  # noqa: E402

_job = load_service_module("core_scorer_app", "core-scorer", "outcome_job")


def measured(horizon: int) -> HorizonOutcome:
    return HorizonOutcome(horizon, "measured", entry_price=1.0, exit_price=1.01, candles_used=12)


def test_fine_interval_leaves_every_horizon_untouched() -> None:
    rows = [measured(15), measured(60), measured(240)]
    assert _job.guard_coarse(rows, "1m") == rows


def test_a_coarse_measurement_says_so_on_the_row() -> None:
    """A 5m-entry result must never be averaged with 1m ones unknowingly."""
    out = _job.guard_coarse([measured(60), measured(240)], "5m")
    assert all(h.status == "measured" for h in out)
    assert all("measured at 5m" in h.reason for h in out)


def test_a_15m_horizon_is_not_measured_five_minutes_late() -> None:
    """Entry up to a third of the window late is a different measurement."""
    out = _job.guard_coarse([measured(15)], "5m")
    assert out[0].status == "insufficient_candles"
    assert "too coarse for a 15m horizon" in out[0].reason
    assert out[0].entry_price is None


def test_a_still_open_horizon_stays_pending_whatever_the_interval() -> None:
    pending = HorizonOutcome(15, "pending", reason="horizon closes in 200s; not measured early")
    assert _job.guard_coarse([pending], "5m") == [pending]


def test_a_coarse_gap_is_still_a_gap() -> None:
    gap = HorizonOutcome(240, "insufficient_candles", reason="candles span 3000s of a 14400s horizon")
    out = _job.guard_coarse([gap], "5m")
    assert out[0].status == "insufficient_candles"
    assert out[0].reason == gap.reason
