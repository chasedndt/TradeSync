"""Scheduled economic events, normalised into one card shape.

Two feeds, kept apart by ``source`` so the operator can see which one a line
came from:

- **ForexFactory** publishes a weekly JSON (``ff_calendar_thisweek.json``) with
  title, currency, an ISO date carrying a UTC offset, an impact rating and the
  forecast/previous figures. Its terms are not published; it is treated as a
  courtesy feed — fetched no more than hourly, cached, and expected to change.
- **FRED** ``releases/dates`` (with ``include_release_dates_with_no_data``)
  lists upcoming official US release dates. Needs the same free key the FRED
  macro provider already wants; dates only, no time of day.

Context only. Nothing here reaches the feature catalog. A pulled payload is
still untrusted: every event is validated field by field and a malformed one
is dropped and counted, never defaulted — an event at a guessed time is worse
than no event.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

IMPACTS = ("High", "Medium", "Low", "Holiday")
FF_FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

# Titles that matter for crypto whatever the impact rating says. Matched
# case-insensitively as substrings. ForexFactory abbreviates ("CPI m/m");
# FRED spells release names out ("Consumer Price Index"), so both forms are
# listed.
MARKET_MOVING = (
    "fomc", "fed chair", "federal funds", "cpi", "consumer price index",
    "core pce", "pce price", "personal income and outlays",
    "non-farm", "nonfarm", "employment situation", "unemployment rate",
    "gdp", "gross domestic product", "ecb", "boe ", "boj ",
    "ppi", "producer price index", "retail sales", "ism ", "treasury",
    "rate decision", "rate statement",
)


@dataclass(frozen=True)
class EventCard:
    title: str
    country: str
    impact: str
    scheduled_at: str  # ISO 8601, UTC
    minutes_until: int
    source: str
    forecast: str = ""
    previous: str = ""
    market_moving: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "country": self.country,
            "impact": self.impact,
            "scheduled_at": self.scheduled_at,
            "minutes_until": self.minutes_until,
            "source": self.source,
            "forecast": self.forecast,
            "previous": self.previous,
            "market_moving": self.market_moving,
        }


@dataclass
class Normalised:
    events: list[EventCard] = field(default_factory=list)
    rejected: int = 0
    rejections: list[str] = field(default_factory=list)


def _is_market_moving(title: str) -> bool:
    lowered = title.lower()
    return any(key in lowered for key in MARKET_MOVING)


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # A time with no offset would silently be read in server-local time and
    # land on the wrong hour; refuse it rather than guess.
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def normalise_forexfactory(
    raw: Any,
    now: datetime,
    *,
    horizon_hours: int = 24 * 8,
    include_past_minutes: int = 60,
) -> Normalised:
    """Validate and convert the ForexFactory weekly feed.

    Keeps events from ``include_past_minutes`` ago (so a release that just
    happened is still visible) to ``horizon_hours`` ahead. Holidays are kept
    but never marked market-moving.
    """
    out = Normalised()
    if not isinstance(raw, list):
        out.rejected = 1
        out.rejections.append("feed body is not a list")
        return out
    now = now.astimezone(timezone.utc)
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            out.rejected += 1
            out.rejections.append(f"#{index}: not an object")
            continue
        title = item.get("title")
        country = item.get("country")
        impact = item.get("impact")
        when = _parse_iso(item.get("date"))
        if not isinstance(title, str) or not title.strip():
            out.rejected += 1
            out.rejections.append(f"#{index}: missing title")
            continue
        if not isinstance(country, str) or not country.strip():
            out.rejected += 1
            out.rejections.append(f"#{index}: missing country")
            continue
        if impact not in IMPACTS:
            out.rejected += 1
            out.rejections.append(f"#{index}: impact {impact!r} not in {IMPACTS}")
            continue
        if when is None:
            out.rejected += 1
            out.rejections.append(f"#{index}: date {item.get('date')!r} not ISO with offset")
            continue
        minutes = int((when - now).total_seconds() // 60)
        if minutes < -include_past_minutes or minutes > horizon_hours * 60:
            continue
        out.events.append(
            EventCard(
                title=title.strip()[:120],
                country=country.strip()[:8],
                impact=impact,
                scheduled_at=when.isoformat(),
                minutes_until=minutes,
                source="forexfactory",
                forecast=str(item.get("forecast") or "")[:24],
                previous=str(item.get("previous") or "")[:24],
                market_moving=impact != "Holiday" and _is_market_moving(title),
            )
        )
    out.events.sort(key=lambda e: e.scheduled_at)
    return out


def normalise_fred_release_dates(
    raw: Any, now: datetime, *, horizon_days: int = 8
) -> Normalised:
    """Convert FRED ``releases/dates`` rows into date-only cards.

    FRED gives a date, not a time; ``scheduled_at`` is midnight UTC of that
    date and ``minutes_until`` counts to it, which the UI shows as a day, not
    an hour. Rows without a release name or date are dropped.
    """
    out = Normalised()
    rows = raw.get("release_dates") if isinstance(raw, Mapping) else None
    if not isinstance(rows, list):
        out.rejected = 1
        out.rejections.append("no release_dates list")
        return out
    now = now.astimezone(timezone.utc)
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            out.rejected += 1
            continue
        name = row.get("release_name")
        date = row.get("date")
        if not isinstance(name, str) or not isinstance(date, str):
            out.rejected += 1
            out.rejections.append(f"#{index}: missing release_name or date")
            continue
        try:
            when = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            out.rejected += 1
            out.rejections.append(f"#{index}: date {date!r} not YYYY-MM-DD")
            continue
        days = (when - now).total_seconds() / 86400
        if days < -1 or days > horizon_days:
            continue
        out.events.append(
            EventCard(
                title=name.strip()[:120],
                country="USD",
                impact="Medium",
                scheduled_at=when.isoformat(),
                minutes_until=int((when - now).total_seconds() // 60),
                source="fred",
                market_moving=_is_market_moving(name),
            )
        )
    out.events.sort(key=lambda e: e.scheduled_at)
    return out


def merge(*parts: Normalised, limit: int = 60) -> dict[str, Any]:
    """Combine feeds into the payload the context endpoint returns."""
    events: list[EventCard] = []
    rejected = 0
    rejections: list[str] = []
    for part in parts:
        events.extend(part.events)
        rejected += part.rejected
        rejections.extend(part.rejections[:5])
    events.sort(key=lambda e: (e.scheduled_at, e.source))
    upcoming = [e for e in events if e.minutes_until >= 0]
    return {
        "metric_family": "economic_calendar",
        "events": [e.to_dict() for e in events[:limit]],
        "next_market_moving": next(
            (e.to_dict() for e in upcoming if e.market_moving), None
        ),
        "counts": {
            "total": len(events),
            "high": sum(1 for e in events if e.impact == "High"),
            "market_moving": sum(1 for e in events if e.market_moving),
            "rejected": rejected,
        },
        "rejections": rejections[:10],
        "sources": sorted({e.source for e in events}),
    }
