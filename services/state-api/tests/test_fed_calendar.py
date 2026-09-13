"""FOMC decision days come from the Fed's calendar, at 2 pm Eastern, and only where the week's feed lacks them."""

from __future__ import annotations

from datetime import datetime, timezone

from app.economic_calendar import normalise_forexfactory
from app.fed_calendar import fomc_decisions

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


def test_the_next_decision_is_added_at_two_pm_eastern() -> None:
    out = fomc_decisions(NOW, [])
    assert [(e.title, e.scheduled_at, e.impact, e.source) for e in out.events] == [
        ("FOMC rate decision", "2026-09-16T18:00:00+00:00", "High", "federalreserve")
    ]
    assert out.events[0].market_moving and out.events[0].minutes_until == 3 * 24 * 60 + 6 * 60


def test_a_decision_the_feed_already_lists_is_not_added_twice() -> None:
    feed = normalise_forexfactory(
        [{"title": "FOMC Statement", "country": "USD", "date": "2026-09-16T14:00:00-04:00", "impact": "High"}], NOW
    )
    assert fomc_decisions(NOW, feed.events).events == []


def test_only_decisions_inside_the_window_are_added() -> None:
    assert fomc_decisions(datetime(2026, 9, 20, tzinfo=timezone.utc), []).events == []
