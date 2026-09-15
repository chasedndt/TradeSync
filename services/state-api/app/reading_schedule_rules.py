"""When a scheduled Hermes reading of a timeframe band is due.

A schedule is a daily time in UTC for one market and band. It acts on the first
daily slot after it was last changed, and once per slot: the loop claims the slot
before it starts anything, so a restart never starts the same slot twice. A slot
the state API could not reach within ``GRACE`` of its time is recorded as missed
rather than started late, because a reading hours late is not the reading the
operator scheduled.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone

GRACE = timedelta(minutes=30)
TIME_RE = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])$")


def parse_time(text: str) -> time:
    match = TIME_RE.fullmatch(text or "")
    if not match:
        raise ValueError("daily_time must be HH:MM in UTC, from 00:00 to 23:59")
    return time(int(match.group(1)), int(match.group(2)))


def time_text(value: time | None) -> str | None:
    return value.strftime("%H:%M") if isinstance(value, time) else None


def iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if isinstance(value, datetime) else None


def slot_on(day: date, daily_time: time) -> datetime:
    return datetime.combine(day, daily_time.replace(tzinfo=None), tzinfo=timezone.utc)


def next_slot(now: datetime, daily_time: time, armed_at: datetime, last_slot: datetime | None) -> datetime:
    """The slot the schedule acts on next: after its last change, after the last slot handled, and not past its grace."""
    first_day = (now - GRACE).date()
    for offset in range(3):
        slot = slot_on(first_day + timedelta(days=offset), daily_time)
        if slot > armed_at and (last_slot is None or slot > last_slot) and now - slot <= GRACE:
            return slot
    return slot_on(first_day + timedelta(days=3), daily_time)


def due_slot(now: datetime, daily_time: time, armed_at: datetime, last_slot: datetime | None) -> datetime | None:
    slot = next_slot(now, daily_time, armed_at, last_slot)
    return slot if slot <= now else None


def missed_slot(now: datetime, daily_time: time, armed_at: datetime, last_slot: datetime | None) -> datetime | None:
    """The latest slot that passed its grace unhandled since the schedule was last changed, if there is one."""
    for offset in range(2):
        slot = slot_on(now.date() - timedelta(days=offset), daily_time)
        if now - slot > GRACE and slot > armed_at and (last_slot is None or slot > last_slot):
            return slot
    return None
