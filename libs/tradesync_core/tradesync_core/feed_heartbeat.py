"""Heartbeats for a live feed or loop: state, last message, last success, counts over the last hour, reconnects, last error.

Held in memory by the service that runs the feed and served as plain data, so the
integration pipeline page can say whether each feed is connected and when it last
delivered anything. Counts begin when the process starts, and the snapshot says
when that was. A heartbeat decides nothing and carries no authority of its own:
``scoring_influence`` and ``influence`` only describe what the feed's data is
used for elsewhere.
"""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Iterable

WINDOW_S = 3600
CONNECTED_STATES = frozenset({"connected", "ok"})


def iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts is not None else None


def describe_error(error: object) -> str:
    """An exception as its type, with the HTTP status when it carries one; a message is kept only when given as text."""
    if isinstance(error, BaseException):
        response = getattr(error, "response", None)
        code = getattr(response, "status_code", None) or getattr(error, "status_code", None)
        return f"{type(error).__name__} (HTTP {code})" if code else type(error).__name__
    return str(error)[:200]


class RollingCount:
    """A count over the last hour, kept in one-minute buckets."""

    def __init__(self, window_s: int = WINDOW_S) -> None:
        self.minutes = max(1, window_s // 60)
        self._buckets: deque[list[int]] = deque()

    def add(self, n: int = 1, now: float | None = None) -> None:
        minute = int((time.time() if now is None else now) // 60)
        if self._buckets and self._buckets[-1][0] >= minute:
            self._buckets[-1][1] += n
        else:
            self._buckets.append([minute, n])
        self._trim(minute)

    def total(self, now: float | None = None) -> int:
        self._trim(int((time.time() if now is None else now) // 60))
        return sum(count for _, count in self._buckets)

    def _trim(self, minute: int) -> None:
        while self._buckets and self._buckets[0][0] <= minute - self.minutes:
            self._buckets.popleft()


class Heartbeat:
    """One feed's heartbeat, updated by the code that runs the feed."""

    def __init__(self, feed_id: str, *, label: str, kind: str, service: str, authority: str, influence: str,
                 scoring_influence: bool = False, counts: Iterable[str] = ("messages",)) -> None:
        self.id, self.label, self.kind, self.service = feed_id, label, kind, service
        self.authority, self.influence, self.scoring_influence = authority, influence, scoring_influence
        self.state = "not_started"
        self.since: float | None = None
        self.connected_at: float | None = None
        self.last_message_at: float | None = None
        self.last_success_at: float | None = None
        self.last_error: str | None = None
        self.last_error_at: float | None = None
        self.attempts = 0
        self.reconnects = 0
        self.detail: dict[str, Any] = {}
        self._counts: dict[str, RollingCount] = {name: RollingCount() for name in counts}

    @staticmethod
    def _now(now: float | None) -> float:
        return time.time() if now is None else now

    def _enter(self, state: str, now: float) -> None:
        if state != self.state:
            self.state, self.since = state, now

    def connecting(self, now: float | None = None) -> None:
        """A connection attempt; every attempt after the first counts as a reconnect."""
        now = self._now(now)
        if self.attempts:
            self.reconnects += 1
        self.attempts += 1
        self.connected_at = None
        self._enter("connecting", now)

    def connected(self, now: float | None = None) -> None:
        now = self._now(now)
        self.connected_at = now
        self._enter("connected", now)

    def message(self, n: int = 1, counter: str = "messages", now: float | None = None) -> None:
        now = self._now(now)
        self.last_message_at = now
        self.count(counter, n, now)

    def count(self, counter: str, n: int = 1, now: float | None = None) -> None:
        if n:
            self._counts.setdefault(counter, RollingCount()).add(n, self._now(now))

    def succeeded(self, now: float | None = None, **counts: int) -> None:
        """A fetch or pass that worked, with what it counted (``rows=500``)."""
        now = self._now(now)
        self.last_success_at = now
        self._enter("ok", now)
        for counter, n in counts.items():
            self.count(counter, n, now)

    def error(self, error: object, now: float | None = None) -> None:
        """Record an error without changing the state: part of a pass failed, the rest worked."""
        self.last_error = describe_error(error)
        self.last_error_at = self._now(now)

    def failed(self, error: object, state: str = "failed", now: float | None = None) -> None:
        now = self._now(now)
        self.error(error, now)
        self.connected_at = None
        self._enter(state, now)

    def snapshot(self, now: float | None = None) -> dict[str, Any]:
        now = self._now(now)
        return {
            "id": self.id, "label": self.label, "kind": self.kind, "service": self.service,
            "state": self.state, "connected": self.state in CONNECTED_STATES, "state_since": iso(self.since),
            "connected_since": iso(self.connected_at), "last_message_at": iso(self.last_message_at),
            "last_success_at": iso(self.last_success_at),
            "counts_1h": {name: count.total(now) for name, count in self._counts.items()},
            "attempts": self.attempts, "reconnects": self.reconnects,
            "last_error": self.last_error, "last_error_at": iso(self.last_error_at),
            "authority": self.authority, "scoring_influence": self.scoring_influence, "influence": self.influence,
            "detail": dict(self.detail),
        }


class Registry:
    """Every heartbeat one service keeps, in the order they were declared."""

    def __init__(self, service: str) -> None:
        self.service = service
        self.started_at = time.time()
        self._feeds: dict[str, Heartbeat] = {}

    def feed(self, feed_id: str, **meta: Any) -> Heartbeat:
        if feed_id not in self._feeds:
            self._feeds[feed_id] = Heartbeat(feed_id, service=self.service, **meta)
        return self._feeds[feed_id]

    def snapshot(self, now: float | None = None) -> dict[str, Any]:
        now = time.time() if now is None else now
        return {"schema_version": "feed_heartbeats_v1", "service": self.service, "generated_at": iso(now),
                "counting_since": iso(self.started_at), "window_seconds": WINDOW_S,
                "feeds": [feed.snapshot(now) for feed in self._feeds.values()]}
