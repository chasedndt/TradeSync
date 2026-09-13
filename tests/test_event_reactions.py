"""Past event reactions are measured from the close before the release, beside ordinary days."""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from tradesync_core.event_reactions import (
    EVENT_KINDS,
    HOUR,
    _by_close,
    baseline_moves,
    guidance,
    kind_for_event,
    kind_for_title,
    profile,
    release_instant_s,
    window_move,
)

T0 = int(datetime(2026, 3, 1, tzinfo=timezone.utc).timestamp())
DAY = 86400


def candles(days: int, bumps: dict[int, float] | None = None, drop: set[int] | None = None):
    """Flat hourly candles at 100; ``bumps`` maps a close time to a percent move on that candle."""
    out, p = [], 100.0
    for i in range(days * 24):
        t = T0 + i * HOUR
        o = p
        if bumps and (t + HOUR) in bumps:
            p = p * (1 + bumps[t + HOUR] / 100)
        if drop and (t + HOUR) in drop:
            continue
        out.append({"time": t, "open": o, "high": max(o, p), "low": min(o, p), "close": p})
    return out


def test_calendar_titles_map_to_event_kinds() -> None:
    assert kind_for_title("CPI m/m").key == "cpi"
    assert kind_for_title("Core PCE Price Index m/m").key == "pce"
    assert kind_for_title("Non-Farm Employment Change").key == "nfp"
    assert kind_for_title("Unemployment Claims").key == "jobless_claims"
    assert kind_for_title("FOMC Statement").key == "fomc"
    assert kind_for_title("Federal Funds Rate").key == "fomc"
    assert kind_for_title("German ZEW Economic Sentiment") is None
    # FRED spells its releases out.
    assert kind_for_title("Advance Monthly Sales for Retail and Food Services").key == "retail_sales"
    assert kind_for_title("Unemployment Insurance Weekly Claims Report").key == "jobless_claims"


def test_an_event_needs_the_right_country_and_for_fomc_a_decision_day() -> None:
    assert kind_for_event({"title": "CPI m/m", "country": "USD"}).key == "cpi"
    assert kind_for_event({"title": "CPI m/m"}).key == "cpi"
    assert kind_for_event({"title": "CPI m/m", "country": "CAD"}) is None
    assert kind_for_event({"title": "PPI m/m", "country": "CHF"}) is None
    assert kind_for_event({"title": "FOMC Press Release", "country": "USD", "scheduled_at": "2026-09-14T00:00:00+00:00"}) is None
    assert kind_for_event({"title": "FOMC Statement", "country": "USD", "scheduled_at": "2026-09-16T18:00:00+00:00"}).key == "fomc"
    assert kind_for_event({"title": "FOMC Meeting Minutes", "country": "USD", "scheduled_at": "2026-10-07T18:00:00+00:00"}) is None


def test_release_instant_uses_us_eastern_time_including_daylight_saving() -> None:
    t = release_instant_s(date(2026, 3, 11), EVENT_KINDS["cpi"], ZoneInfo("America/New_York"))
    at = datetime.fromtimestamp(t, tz=timezone.utc)
    assert (at.hour, at.minute) == (12, 30)  # 08:30 EDT
    t = release_instant_s(date(2026, 1, 28), EVENT_KINDS["fomc"], ZoneInfo("America/New_York"))
    assert datetime.fromtimestamp(t, tz=timezone.utc).hour == 19  # 14:00 EST


def test_window_move_runs_from_the_close_before_the_release_and_refuses_gaps() -> None:
    instant = T0 + 5 * DAY + 8 * HOUR + 1800  # 08:30
    bump_close = T0 + 5 * DAY + 9 * HOUR
    by_close = _by_close(candles(10, {bump_close: 2.0}))
    m = window_move(by_close, instant, 1)
    assert abs(m["move_pct"] - 2.0) < 1e-9 and m["range_pct"] >= 2.0
    assert window_move(by_close, T0 + 30 * DAY, 1) is None
    gapped = _by_close(candles(10, {bump_close: 2.0}, drop={bump_close}))
    assert window_move(gapped, instant, 1) is None


def _event_book():
    event_days = [2, 6, 10, 14, 18, 22]
    bumps = {}
    for d in range(30):
        close = T0 + d * DAY + 9 * HOUR
        if d in event_days:
            bumps[close] = 3.0 if event_days.index(d) % 2 == 0 else -3.0
        else:
            bumps[close] = 0.5 if d % 2 == 0 else -0.5
    instants = [T0 + d * DAY + 8 * HOUR + 1800 for d in event_days]
    return candles(30, bumps), instants


def test_profile_reports_volatility_expansion_and_direction_split_against_ordinary_days() -> None:
    c, instants = _event_book()
    p = profile(EVENT_KINDS["cpi"], instants, c, instants)
    h = p["horizons"]["4h"]
    assert h["n"] == 6
    assert abs(h["median_abs_move_pct"] - 3.0) < 0.01
    assert abs(h["baseline_median_abs_move_pct"] - 0.5) < 0.01
    assert h["volatility_ratio"] == 6.0 and h["up_share"] == 0.5
    assert len(p["occurrences"]) == 6


def test_baseline_skips_days_near_any_release() -> None:
    c, instants = _event_book()
    moves = baseline_moves(_by_close(c), instants, 4, instants)
    assert moves and all(abs(m - 0.5) < 0.01 for m in moves)


def test_guidance_says_what_to_do_and_admits_small_samples() -> None:
    c, instants = _event_book()
    g = guidance("US CPI", "BTC", profile(EVENT_KINDS["cpi"], instants, c, instants))
    assert "6.0×" in g and "no consistent direction" in g and "stand aside" in g and "median of 6" in g
    few = profile(EVENT_KINDS["cpi"], instants[:2], c, instants)
    assert "too few to judge" in guidance("US CPI", "BTC", few)
