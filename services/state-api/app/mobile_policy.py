"""Pure notification preference checks; no provider or trading authority."""
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, Field, field_validator


class Preferences(BaseModel):
    paper_events: bool = False
    timezone: str = 'Europe/London'
    quiet_start: int = Field(22, ge=0, le=23)
    quiet_end: int = Field(8, ge=0, le=23)
    quiet_enabled: bool = True
    daily_budget: int = Field(10, ge=1, le=50)

    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('Use a valid IANA timezone, for example Europe/London')
        return value


def quiet(preferences: Preferences, now: datetime):
    if now.tzinfo is None:
        raise ValueError('Timezone-aware clock required')
    if not preferences.quiet_enabled:
        return False
    hour = now.astimezone(ZoneInfo(preferences.timezone)).hour
    start, end = preferences.quiet_start, preferences.quiet_end
    if start == end:
        return True  # An equal enabled interval means all-day quiet, not no quiet.
    return start <= hour < end if start < end else hour >= start or hour < end
