"""Scheduled Hermes readings: off by default, changed with an audit row, started once per daily slot, skipped with a reason."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import agent_connector, horizon_reading, horizons, reading_schedule
from app import reading_schedule_rules as rules
from app import reading_schedule_store as store
from app.main import app, state

client = TestClient(app)
UTC = timezone.utc
MEASURED = (datetime.now(UTC) - timedelta(minutes=1)).replace(microsecond=0)


@pytest.fixture(autouse=True)
def memory(monkeypatch):
    monkeypatch.setattr(store, "_memory", {})
    monkeypatch.setattr(store, "_audit_memory", [])
    monkeypatch.setattr(state, "pool", None)


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def schedule(scope: str, daily: time, armed: datetime, enabled: bool = True) -> None:
    asyncio.run(store.save(None, "BTC-PERP", scope, enabled, daily, "chase", armed))


def minutes_ago(now: datetime, minutes: int) -> time:
    slot = now - timedelta(minutes=minutes)
    return time(slot.hour, slot.minute)


def measured_entry():
    return {"at": MEASURED.timestamp(), "outlook": {"available": True}, "evaluation": {}}


def test_a_slot_is_due_once_after_the_schedule_was_set_and_only_within_its_grace() -> None:
    eight, armed = time(8, 0), at("2026-09-14 12:00")
    assert rules.next_slot(at("2026-09-15 07:00"), eight, armed, None) == at("2026-09-15 08:00")
    assert rules.due_slot(at("2026-09-15 07:59"), eight, armed, None) is None
    assert rules.due_slot(at("2026-09-15 08:10"), eight, armed, None) == at("2026-09-15 08:00")
    assert rules.due_slot(at("2026-09-15 08:10"), eight, armed, at("2026-09-15 08:00")) is None  # already handled
    assert rules.next_slot(at("2026-09-15 08:10"), eight, armed, at("2026-09-15 08:00")) == at("2026-09-16 08:00")
    assert rules.due_slot(at("2026-09-15 08:31"), eight, armed, None) is None  # past its grace: not started late
    assert rules.missed_slot(at("2026-09-15 08:31"), eight, armed, None) == at("2026-09-15 08:00")
    assert rules.missed_slot(at("2026-09-15 08:10"), eight, armed, None) is None


def test_a_change_after_the_time_waits_for_the_next_day_and_slots_cross_midnight() -> None:
    eight = time(8, 0)
    assert rules.due_slot(at("2026-09-15 08:06"), eight, at("2026-09-15 08:05"), None) is None
    assert rules.next_slot(at("2026-09-15 08:06"), eight, at("2026-09-15 08:05"), None) == at("2026-09-16 08:00")
    assert rules.due_slot(at("2026-09-16 00:10"), time(23, 50), at("2026-09-14 09:00"), None) == at("2026-09-15 23:50")


def test_times_must_be_hh_mm_on_the_clock() -> None:
    assert rules.parse_time("08:05") == time(8, 5) and rules.time_text(time(7, 30)) == "07:30"
    for bad in ("8:05", "24:00", "07:60", "0805", "", "08:05:00"):
        with pytest.raises(ValueError):
            rules.parse_time(bad)


def test_every_band_is_off_until_an_operator_sets_it_and_each_change_is_audited() -> None:
    first = client.get("/state/market/horizons/reading-schedule?symbol=btc-perp").json()
    assert first["symbol"] == "BTC-PERP" and first["timezone"] == "UTC" and first["changes"] == []
    assert set(first["bands"]) == {"short", "lower", "medium", "higher"}
    assert all(band == {"enabled": False, "daily_time": None, "next_reading_at": None, "updated_by": None, "updated_at": None, "last": None}
               for band in first["bands"].values())

    on = client.put("/state/market/horizons/reading-schedule",
                    json={"symbol": "BTC-PERP", "scope": "lower", "enabled": True, "daily_time": "07:30", "changed_by": "chase"})
    body = on.json()
    assert on.status_code == 200 and body["previous"] is None and body["changed_by"] == "chase"
    assert body["schedule"]["enabled"] and body["schedule"]["daily_time"] == "07:30"
    next_at = datetime.fromisoformat(body["schedule"]["next_reading_at"])
    assert next_at > datetime.fromisoformat(body["changed_at"]) and (next_at.hour, next_at.minute) == (7, 30)

    off = client.put("/state/market/horizons/reading-schedule",
                     json={"symbol": "BTC-PERP", "scope": "lower", "enabled": False, "daily_time": "07:30"}).json()
    assert off["previous"] == {"enabled": True, "daily_time": "07:30"} and off["schedule"]["next_reading_at"] is None
    assert off["changed_by"] == "operator"

    page = client.get("/state/market/horizons/reading-schedule?symbol=BTC-PERP").json()
    assert [(c["scope"], c["changed_by"], c["previous"], c["next"]) for c in page["changes"]] == [
        ("lower", "operator", {"enabled": True, "daily_time": "07:30"}, {"enabled": False, "daily_time": "07:30"}),
        ("lower", "chase", None, {"enabled": True, "daily_time": "07:30"}),
    ]
    assert page["bands"]["lower"]["daily_time"] == "07:30" and not page["bands"]["lower"]["enabled"]
    assert not page["bands"]["short"]["enabled"] and page["changes"][0]["changed_at"]
    assert client.get("/state/market/horizons/reading-schedule?symbol=ETH-PERP").json()["changes"] == []


def test_bad_input_is_refused_and_leaves_no_audit_row() -> None:
    def put(**change):
        return client.put("/state/market/horizons/reading-schedule",
                          json={"symbol": "BTC-PERP", "scope": "short", "enabled": True, "daily_time": "08:00", **change})

    assert put(daily_time="25:00").status_code == 400
    assert put(scope="yearly").status_code == 422
    assert put(symbol="../etc").status_code == 400
    assert store._audit_memory == [] and store._memory == {}


def test_a_due_band_starts_one_reading_through_the_page_logic_and_never_twice_for_its_slot() -> None:
    now = datetime.now(UTC)
    schedule("short", minutes_ago(now, 5), now - timedelta(days=1))
    start = AsyncMock(return_value={"status": "started", "reading": {}})
    with patch.object(agent_connector, "configured", return_value=True), \
            patch.object(horizons, "part_or_error", AsyncMock(return_value=(measured_entry(), None))) as part, \
            patch.object(horizon_reading, "latest", AsyncMock(return_value={"short": {"status": "none"}})), \
            patch.object(horizon_reading, "start", start):
        first = asyncio.run(reading_schedule.run_due(None, "http://md", now))
        again = asyncio.run(reading_schedule.run_due(None, "http://md", now + timedelta(minutes=1)))
    assert [(h["scope"], h["result"]) for h in first] == [("short", "started")] and again == []
    start.assert_awaited_once()
    assert start.await_args.args[:3] == (None, "BTC-PERP", "short") and start.await_args.args[5] == MEASURED
    assert part.await_args.args == ("http://md", "BTC-PERP", "short")
    band = reading_schedule.band_view(asyncio.run(store.for_symbol(None, "BTC-PERP"))["short"], now)
    assert band["last"]["result"] == "started" and "reading the measurement of" in band["last"]["detail"]
    assert datetime.fromisoformat(band["next_reading_at"]) > now


@pytest.mark.parametrize("latest, configured, expected", [
    ({"short": {"status": "running"}}, True, "a reading is already running"),
    ({"short": {"status": "ok", "measured_at": MEASURED.isoformat()}}, True, "already exists"),
    ({"short": {"status": "none"}}, False, "the Hermes gateway is not configured"),
])
def test_a_due_band_is_skipped_with_the_reason(latest, configured, expected) -> None:
    now = datetime.now(UTC)
    schedule("short", minutes_ago(now, 5), now - timedelta(days=1))
    start = AsyncMock()
    with patch.object(agent_connector, "configured", return_value=configured), \
            patch.object(horizons, "part_or_error", AsyncMock(return_value=(measured_entry(), None))), \
            patch.object(horizon_reading, "latest", AsyncMock(return_value=latest)), \
            patch.object(horizon_reading, "start", start):
        [handled] = asyncio.run(reading_schedule.run_due(None, "http://md", now))
    assert handled["result"] == "skipped" and expected in handled["detail"]
    start.assert_not_awaited()


def test_a_slot_missed_past_its_grace_is_recorded_not_started_and_an_off_band_is_never_read() -> None:
    now = datetime.now(UTC)
    schedule("lower", minutes_ago(now, 120), now - timedelta(days=1))
    schedule("medium", minutes_ago(now, 5), now - timedelta(days=1), enabled=False)
    start = AsyncMock()
    with patch.object(agent_connector, "configured", return_value=True), patch.object(horizon_reading, "start", start):
        handled = asyncio.run(reading_schedule.run_due(None, "http://md", now))
    assert [(h["scope"], h["result"]) for h in handled] == [("lower", "missed")]
    start.assert_not_awaited()
    band = reading_schedule.band_view(asyncio.run(store.for_symbol(None, "BTC-PERP"))["lower"], now)
    assert band["last"]["result"] == "missed" and datetime.fromisoformat(band["next_reading_at"]) > now


class TxConn:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []

    def transaction(self):
        @asynccontextmanager
        async def transaction():
            yield

        return transaction()

    async def fetchrow(self, sql, *args):
        if "FOR UPDATE" in sql:
            return {"enabled": False, "daily_time": time(7, 30)}
        return {"symbol": args[0], "scope": args[1], "enabled": args[2], "daily_time": args[3], "updated_by": args[4],
                "updated_at": args[5], "last_slot": None, "last_result": None, "last_detail": None}

    async def execute(self, sql, *args):
        self.executed.append((sql, args))

    async def fetchval(self, sql, *args):
        self.executed.append((sql, args))
        return None


def test_with_a_database_the_change_and_its_audit_row_are_written_together() -> None:
    conn = TxConn()
    pool = MagicMock()

    @asynccontextmanager
    async def acquire():
        yield conn

    pool.acquire = acquire
    now = datetime.now(UTC)
    row, previous = asyncio.run(store.save(pool, "BTC-PERP", "higher", True, time(9, 15), "chase", now))
    assert previous == {"enabled": False, "daily_time": "07:30"} and row["daily_time"] == time(9, 15)
    [(sql, args)] = conn.executed
    assert "horizon_reading_schedule_audit" in sql and args[:4] == ("BTC-PERP", "higher", "chase", now)
    assert args[4] == '{"enabled": false, "daily_time": "07:30"}' and args[5] == '{"enabled": true, "daily_time": "09:15"}'
    # a slot is claimed only while the schedule is unchanged since it was read
    assert asyncio.run(store.claim(pool, "BTC-PERP", "higher", now, now - timedelta(days=1), "starting", "")) is False
