"""A pulled calendar is untrusted input: validate every event, default nothing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.economic_calendar import (
    merge,
    normalise_forexfactory,
    normalise_fred_release_dates,
)

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


def ff(title="CPI m/m", country="USD", date="2026-09-12T08:30:00-04:00", impact="High", **extra):
    return {"title": title, "country": country, "date": date, "impact": impact,
            "forecast": "0.3%", "previous": "0.2%", **extra}


def test_offset_dates_are_converted_to_utc_and_counted_down() -> None:
    out = normalise_forexfactory([ff()], NOW)
    assert out.rejected == 0
    event = out.events[0]
    # 08:30 at -04:00 is 12:30 UTC, thirty minutes from NOW.
    assert event.scheduled_at == "2026-09-12T12:30:00+00:00"
    assert event.minutes_until == 30
    assert event.market_moving is True


def test_a_date_without_an_offset_is_refused_not_guessed() -> None:
    """Read in server-local time it would land on the wrong hour."""
    out = normalise_forexfactory([ff(date="2026-09-12T08:30:00")], NOW)
    assert out.events == []
    assert out.rejected == 1
    assert "not ISO with offset" in out.rejections[0]


def test_unknown_impact_missing_title_and_non_objects_are_dropped_and_counted() -> None:
    raw = [ff(impact="Extreme"), ff(title=""), "not an object", ff(title="ok", impact="Low")]
    out = normalise_forexfactory(raw, NOW)
    assert [e.title for e in out.events] == ["ok"]
    assert out.rejected == 3


def test_a_feed_that_is_not_a_list_is_rejected_whole() -> None:
    out = normalise_forexfactory({"events": []}, NOW)
    assert out.events == [] and out.rejected == 1


def test_window_keeps_the_last_hour_and_the_next_eight_days() -> None:
    raw = [
        ff(title="two hours ago", date=(NOW - timedelta(hours=2)).isoformat()),
        ff(title="thirty min ago", date=(NOW - timedelta(minutes=30)).isoformat()),
        ff(title="next week", date=(NOW + timedelta(days=7)).isoformat()),
        ff(title="too far", date=(NOW + timedelta(days=9)).isoformat()),
    ]
    out = normalise_forexfactory(raw, NOW)
    assert [e.title for e in out.events] == ["thirty min ago", "next week"]


def test_holidays_are_kept_but_never_market_moving() -> None:
    out = normalise_forexfactory([ff(title="Bank Holiday CPI", impact="Holiday")], NOW)
    assert out.events[0].impact == "Holiday"
    assert out.events[0].market_moving is False


def test_spelled_out_release_names_are_recognised_like_abbreviations() -> None:
    """FRED says "Consumer Price Index"; ForexFactory says "CPI m/m". Both count."""
    out = normalise_forexfactory(
        [ff(title="Consumer Price Index"), ff(title="Employment Situation"), ff(title="CPI m/m")],
        NOW,
    )
    assert all(e.market_moving for e in out.events)


def test_keywords_match_whole_words_not_fragments() -> None:
    """'CBOE Market Statistics' contains 'boe'; it is an exchange, not the Bank of England."""
    out = normalise_forexfactory(
        [ff(title="CBOE Market Statistics"), ff(title="BoE Gov Bailey Speaks"), ff(title="ISM Manufacturing PMI")],
        NOW,
    )
    assert {e.title: e.market_moving for e in out.events} == {
        "CBOE Market Statistics": False, "BoE Gov Bailey Speaks": True, "ISM Manufacturing PMI": True,
    }


def test_market_moving_is_by_title_not_by_feed_rating() -> None:
    low_but_matters = ff(title="FOMC Member Speaks", impact="Low")
    high_but_not = ff(title="ANZ Job Advertisements m/m", impact="High", country="AUD")
    out = normalise_forexfactory([low_but_matters, high_but_not], NOW)
    by_title = {e.title: e.market_moving for e in out.events}
    assert by_title == {"FOMC Member Speaks": True, "ANZ Job Advertisements m/m": False}


def test_fred_release_dates_become_date_only_cards() -> None:
    raw = {"release_dates": [
        {"release_id": 10, "release_name": "Consumer Price Index", "date": "2026-09-15"},
        {"release_id": 11, "release_name": "Old", "date": "2026-09-01"},
        {"release_id": 12, "date": "2026-09-16"},
        {"release_id": 13, "release_name": "Bad", "date": "15/09/2026"},
    ]}
    out = normalise_fred_release_dates(raw, NOW)
    assert [e.title for e in out.events] == ["Consumer Price Index"]
    assert out.events[0].scheduled_at == "2026-09-15T00:00:00+00:00"
    assert out.events[0].source == "fred" and out.events[0].market_moving
    assert out.rejected == 2


def test_merge_orders_by_time_and_names_the_next_market_mover() -> None:
    ff_part = normalise_forexfactory(
        [ff(title="Retail Sales m/m", date=(NOW + timedelta(hours=5)).isoformat()),
         ff(title="Leading Indicators", impact="Low", date=(NOW + timedelta(hours=1)).isoformat())],
        NOW,
    )
    fred_part = normalise_fred_release_dates(
        {"release_dates": [{"release_name": "Gross Domestic Product", "date": "2026-09-14"}]}, NOW
    )
    payload = merge(ff_part, fred_part)
    assert [e["title"] for e in payload["events"]] == [
        "Leading Indicators", "Retail Sales m/m", "Gross Domestic Product"
    ]
    assert payload["next_market_moving"]["title"] == "Retail Sales m/m"
    # Retail Sales and GDP are market-moving by title; Leading Indicators is not.
    assert payload["counts"] == {"total": 3, "high": 1, "market_moving": 2, "rejected": 0}
    assert payload["sources"] == ["forexfactory", "fred"]


def test_merge_with_nothing_is_an_empty_calendar_not_an_error() -> None:
    payload = merge(normalise_forexfactory([], NOW))
    assert payload["events"] == [] and payload["next_market_moving"] is None
