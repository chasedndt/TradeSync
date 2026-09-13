"""FOMC decision days from the Federal Reserve's published calendar, as calendar cards.

ForexFactory's feed covers the current week only, and FRED's "FOMC Press
Release" is a data series that updates every business day, not the decision.
The Fed publishes its meeting calendar a year ahead. The decision days live
once, in ``tradesync_core.event_reactions``, where the measured reaction record
uses the same list; this module only turns the upcoming ones into cards, at
2 pm US Eastern, and skips a day the week's feed already lists.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.economic_calendar import EventCard, Normalised
from tradesync_core.event_reactions import EVENT_KINDS, kind_for_event, release_instant_s

FOMC = EVENT_KINDS["fomc"]


def fomc_decisions(now: datetime, existing: Sequence[EventCard], *, horizon_days: int = 8) -> Normalised:
    """Upcoming decision days inside the window that no existing card already covers."""
    out = Normalised()
    try:
        eastern = ZoneInfo("America/New_York")
    except ZoneInfoNotFoundError:
        out.rejections.append("no timezone database; FOMC decision times not computed")
        return out
    now = now.astimezone(timezone.utc)
    covered = {e.scheduled_at[:10] for e in existing if kind_for_event(e.to_dict()) is FOMC}
    for day_text in FOMC.fixed_dates:
        instant = datetime.fromtimestamp(release_instant_s(date.fromisoformat(day_text), FOMC, eastern), timezone.utc)
        minutes = int((instant - now).total_seconds() // 60)
        if minutes < -60 or minutes > horizon_days * 24 * 60 or day_text in covered:
            continue
        out.events.append(EventCard(
            title="FOMC rate decision",
            country="USD",
            impact="High",
            scheduled_at=instant.isoformat(),
            minutes_until=minutes,
            source="federalreserve",
            market_moving=True,
            url=FOMC.source_url,
        ))
    return out
