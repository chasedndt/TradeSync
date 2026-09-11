"""A final "no candles" verdict may only follow a request that covered the window."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _service_import import load_service_module  # noqa: E402

from tradesync_core.outcomes import HorizonOutcome  # noqa: E402

_job = load_service_module("core_scorer_app", "core-scorer", "outcome_job")
_windows = load_service_module("core_scorer_app", "core-scorer", "outcome_windows")
FetchRange = _windows.FetchRange

DAY = 86_400


def empty(horizon: int) -> HorizonOutcome:
    return HorizonOutcome(horizon, "insufficient_candles", reason="no candles cover this window")


def test_an_unrequested_empty_window_stays_pending_instead_of_final() -> None:
    fetched = [FetchRange((3 * DAY - 8 * 3600) * 1000, 3 * DAY * 1000)]
    guarded = _job.guard_unrequested([empty(15), empty(240)], fetched, opened_at_s=2 * DAY)
    assert [h.status for h in guarded] == ["pending", "pending"]
    assert all(h.reason == _job.NOT_FETCHED for h in guarded)


def test_a_requested_empty_window_keeps_its_final_verdict() -> None:
    fetched = [FetchRange(0, 3 * DAY * 1000)]
    guarded = _job.guard_unrequested([empty(15)], fetched, opened_at_s=2 * DAY)
    assert guarded[0].status == "insufficient_candles"
    assert guarded[0].reason == "no candles cover this window"


def test_measured_and_pending_horizons_pass_through_untouched() -> None:
    measured = HorizonOutcome(60, "measured", entry_price=1.0, exit_price=1.1, candles_used=60)
    pending = HorizonOutcome(240, "pending", reason="horizon closes in 100s; not measured early")
    assert _job.guard_unrequested([measured, pending], [], opened_at_s=0) == [measured, pending]


def test_a_partially_fetched_window_is_treated_as_not_fetched() -> None:
    """Judging a gap from half a window would report our own request as the venue's hole."""
    fetched = [FetchRange(0, (2 * DAY + 100 * 60) * 1000)]  # ends 100 min into a 240 min window
    guarded = _job.guard_unrequested([empty(240)], fetched, opened_at_s=2 * DAY)
    assert guarded[0].status == "pending"
