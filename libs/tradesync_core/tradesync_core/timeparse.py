"""One ISO 8601 parser for the whole system.

Three modules had grown their own — the control envelope, the graph snapshot
validator, and the Gate endpoint — each with its own handling of a trailing
``Z`` and its own opinion about naive timestamps. Three parsers for one fact is
how two of them end up disagreeing about what "2026-09-08T21:00:00" means, and
for a system whose windows are measured in hours that disagreement is the whole
window.

The rules, in one place:

- A trailing ``Z`` is accepted. ``datetime.fromisoformat`` did not take one
  before Python 3.11 and external systems emit it constantly.
- A naive timestamp is **refused**, not assumed to be UTC. "Assume UTC" is
  right until the one time it is not, and the failure is silent by hours.
- The result is always normalised to UTC, so comparisons downstream cannot be
  wrong about an offset.
"""

from __future__ import annotations

from datetime import datetime, timezone


class TimestampError(ValueError):
    """A timestamp could not be read, with the field named."""


def parse_utc(value: object, field: str = "timestamp") -> datetime:
    """Parse an ISO 8601 timestamp and normalise it to UTC."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise TimestampError(f"{field} must include a UTC offset")
        return value.astimezone(timezone.utc)

    if not isinstance(value, str) or not value.strip():
        raise TimestampError(f"{field} must be an ISO 8601 string")

    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise TimestampError(f"{field} is not ISO 8601: {exc}") from exc

    if parsed.tzinfo is None:
        raise TimestampError(f"{field} must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def parse_utc_allow_naive(value: object, field: str = "timestamp") -> datetime:
    """As ``parse_utc``, but a naive timestamp is read as UTC.

    Only for reading a value this system itself wrote without an offset. Never
    for anything that crossed a boundary: an external naive timestamp is
    ambiguous, and guessing is how a candidate gets evaluated against candles it
    could not have seen.
    """
    if isinstance(value, str) and value.strip() and not _has_offset(value.strip()):
        try:
            return datetime.fromisoformat(value.strip()).replace(tzinfo=timezone.utc)
        except ValueError as exc:
            # Unparseable, not merely naive. It must still surface as a
            # TimestampError, or callers that catch that see a bare ValueError
            # escape as a server error instead of a stated refusal.
            raise TimestampError(f"{field} is not ISO 8601: {exc}") from exc
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return parse_utc(value, field)


def _has_offset(text: str) -> bool:
    if text.endswith(("Z", "z")):
        return True
    # An offset is +HH:MM or -HH:MM at the end; a date's own hyphens are earlier.
    tail = text[-6:]
    return len(tail) == 6 and tail[0] in "+-" and tail[3] == ":"
