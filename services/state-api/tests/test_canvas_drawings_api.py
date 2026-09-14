"""Canvas drawing endpoints: reads across intervals, stored style, clearing a symbol."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app, state

client = TestClient(app)

T = 1_788_800_000
ID = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"
CREATED = datetime(2026, 9, 14, 9, 30, tzinfo=timezone.utc)
STYLE = {"colour": "#e3b23c", "width": 2, "dashed": False}
A = {"time_s": T, "price": 79000.0}
B = {"time_s": T + 900, "price": 79400.0}


class FakeConn:
    def __init__(self, rows=None, fetchrow=None, execute="UPDATE 0") -> None:
        self.fetch = AsyncMock(return_value=rows or [])
        self.fetchrow = AsyncMock(return_value=fetchrow)
        self.execute = AsyncMock(return_value=execute)

    def transaction(self):
        @asynccontextmanager
        async def transaction():
            yield

        return transaction()


def fake_pool(conn: FakeConn) -> MagicMock:
    pool = MagicMock()

    @asynccontextmanager
    async def acquire():
        yield conn

    pool.acquire = acquire
    return pool


def stored(**changes):
    row = {
        "drawing_id": ID,
        "version": 1,
        "interval": "15m",
        "kind": "trendline",
        "points": json.dumps([A, B]),
        "label": "",
        "colour": "",
        "style": json.dumps(STYLE),
        "created_at": CREATED,
    }
    row.update(changes)
    return row


def test_all_intervals_returns_the_symbols_live_drawings_each_naming_its_interval() -> None:
    conn = FakeConn(rows=[stored(), stored(drawing_id=OTHER, interval="1h", kind="vertical", points=json.dumps([A]))])
    with patch.object(state, "pool", fake_pool(conn)):
        resp = client.get("/state/canvas/drawings", params={"symbol": "btc", "all_intervals": "true"})
    body = resp.json()
    assert resp.status_code == 200 and body["all_intervals"] is True and body["authority"] == "none"
    assert [(d["kind"], d["interval"]) for d in body["drawings"]] == [("trendline", "15m"), ("vertical", "1h")]
    sql, *args = conn.fetch.await_args.args
    assert args == ["BTC-PERP"]
    assert "interval = $2" not in sql and "superseded_at IS NULL AND deleted = false" in sql


def test_one_interval_is_still_read_on_its_own() -> None:
    conn = FakeConn(rows=[stored()])
    with patch.object(state, "pool", fake_pool(conn)):
        resp = client.get("/state/canvas/drawings", params={"symbol": "BTC-PERP", "interval": "15m"})
    body = resp.json()
    assert resp.status_code == 200 and body["interval"] == "15m" and body["all_intervals"] is False
    sql, *args = conn.fetch.await_args.args
    assert args == ["BTC-PERP", "15m"] and "interval = $2" in sql


def test_an_interval_is_required_unless_every_interval_is_asked_for() -> None:
    conn = FakeConn()
    with patch.object(state, "pool", fake_pool(conn)):
        resp = client.get("/state/canvas/drawings", params={"symbol": "BTC-PERP"})
    assert resp.status_code == 422
    conn.fetch.assert_not_awaited()


def test_style_reads_back_as_an_object_and_as_null_for_versions_before_styles() -> None:
    conn = FakeConn(rows=[stored(), stored(drawing_id=OTHER, style=None)])
    with patch.object(state, "pool", fake_pool(conn)):
        body = client.get("/state/canvas/drawings", params={"symbol": "BTC-PERP", "all_intervals": "true"}).json()
    assert body["drawings"][0]["style"] == STYLE and body["drawings"][1]["style"] is None


def test_a_pencil_stroke_is_stored_with_its_style() -> None:
    conn = FakeConn()
    stroke = [{"time_s": T + i * 60, "price": 79000.0 + i * 5} for i in range(12)]
    payload = {"symbol": "BTC-PERP", "interval": "5m", "kind": "pencil", "points": stroke, "style": STYLE}
    with patch.object(state, "pool", fake_pool(conn)):
        resp = client.post("/state/canvas/drawings", json=payload)
    body = resp.json()
    assert resp.status_code == 200 and body["kind"] == "pencil" and body["version"] == 1
    assert body["style"] == STYLE and len(body["points"]) == 12
    args = conn.execute.await_args.args
    assert "INSERT INTO canvas_drawings" in args[0] and "style" in args[0]
    assert args[5] == "pencil" and json.loads(args[9]) == STYLE and args[10] is False


def test_a_drawing_sent_without_a_style_stores_null() -> None:
    conn = FakeConn()
    payload = {"symbol": "BTC-PERP", "interval": "15m", "kind": "trendline", "points": [A, B]}
    with patch.object(state, "pool", fake_pool(conn)):
        resp = client.post("/state/canvas/drawings", json=payload)
    assert resp.status_code == 200 and resp.json()["style"] is None
    assert conn.execute.await_args.args[9] is None


def test_a_malformed_style_or_unlabelled_text_is_refused_before_anything_is_stored() -> None:
    conn = FakeConn()
    bad_style = {"symbol": "BTC-PERP", "interval": "15m", "kind": "rectangle", "points": [A, B],
                 "style": {"colour": "#e3b23c", "width": 9, "dashed": False}}
    no_text = {"symbol": "BTC-PERP", "interval": "15m", "kind": "text", "points": [A], "label": " "}
    with patch.object(state, "pool", fake_pool(conn)):
        refused_style = client.post("/state/canvas/drawings", json=bad_style)
        refused_text = client.post("/state/canvas/drawings", json=no_text)
    assert refused_style.status_code == 400 and "width" in refused_style.json()["detail"]
    assert refused_text.status_code == 400 and "needs a label" in refused_text.json()["detail"]
    conn.execute.assert_not_awaited()


def test_a_move_supersedes_the_live_version_and_stores_the_next_with_its_style() -> None:
    conn = FakeConn(fetchrow={"version": 2})
    moved = {"symbol": "BTC-PERP", "interval": "15m", "kind": "ray", "points": [A, B],
             "style": {"colour": "#4196ff", "width": 3, "dashed": True}}
    with patch.object(state, "pool", fake_pool(conn)):
        resp = client.put(f"/state/canvas/drawings/{ID}", json=moved)
    assert resp.status_code == 200 and resp.json()["version"] == 3
    supersede, insert = conn.execute.await_args_list
    assert "SET superseded_at = now()" in supersede.args[0]
    assert insert.args[2] == 3 and json.loads(insert.args[9]) == moved["style"]


def test_clearing_a_symbol_removes_its_live_drawings_on_every_interval_and_keeps_history() -> None:
    conn = FakeConn(execute="UPDATE 3")
    with patch.object(state, "pool", fake_pool(conn)):
        resp = client.delete("/state/canvas/drawings", params={"symbol": "eth"})
    assert resp.status_code == 200
    assert resp.json() == {"symbol": "ETH-PERP", "deleted": 3, "history_retained": True}
    sql, *args = conn.execute.await_args.args
    assert args == ["ETH-PERP"] and "deleted = true" in sql and "interval" not in sql


def test_clearing_a_symbol_with_nothing_drawn_reports_zero() -> None:
    with patch.object(state, "pool", fake_pool(FakeConn(execute="UPDATE 0"))):
        resp = client.delete("/state/canvas/drawings", params={"symbol": "SOL-PERP"})
    assert resp.status_code == 200 and resp.json()["deleted"] == 0


def test_history_carries_each_versions_style() -> None:
    rows = [
        {**stored(style=None), "superseded_at": CREATED, "deleted": False},
        {**stored(version=2), "superseded_at": None, "deleted": False},
    ]
    with patch.object(state, "pool", fake_pool(FakeConn(rows=rows))):
        body = client.get(f"/state/canvas/drawings/{ID}/history").json()
    assert [v["style"] for v in body["versions"]] == [None, STYLE]
