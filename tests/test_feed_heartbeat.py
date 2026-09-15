"""A feed heartbeat counts over the last hour, counts reconnects, and keeps an error's type rather than its message."""

from __future__ import annotations

import httpx

from tradesync_core.feed_heartbeat import Heartbeat, Registry, RollingCount, describe_error

T = 1_789_400_000.0  # 14 September 2026, 15:33 UTC


def beat(**extra):
    return Heartbeat("hyperliquid_l2book_3", label="Hyperliquid l2Book, 3 significant figures", kind="websocket",
                     service="market-data", authority="display_only", influence="liquidity heatmap", **extra)


def test_a_rolling_count_keeps_only_the_last_hour() -> None:
    count = RollingCount()
    count.add(5, now=T)
    count.add(2, now=T + 30 * 60)
    assert count.total(now=T + 30 * 60) == 7
    assert count.total(now=T + 60 * 60 + 60) == 2  # the first minute has left the hour
    assert count.total(now=T + 3 * 3600) == 0


def test_every_attempt_after_the_first_is_a_reconnect() -> None:
    hb = beat()
    hb.connecting(now=T)
    hb.connected(now=T + 1)
    hb.message(now=T + 2)
    hb.message(3, now=T + 3)
    hb.failed(ConnectionResetError("peer closed"), state="disconnected", now=T + 10)
    assert hb.snapshot(now=T + 11)["connected"] is False
    hb.connecting(now=T + 12)
    hb.connected(now=T + 13)
    snap = hb.snapshot(now=T + 20)
    assert snap["state"] == "connected" and snap["connected"] and snap["reconnects"] == 1 and snap["attempts"] == 2
    assert snap["counts_1h"] == {"messages": 4}
    assert snap["last_error"] == "ConnectionResetError" and snap["last_error_at"].startswith("2026-09-14T15:33")
    assert snap["connected_since"] == snap["state_since"] and snap["scoring_influence"] is False


def test_an_error_keeps_its_type_and_http_status_but_not_its_message() -> None:
    request = httpx.Request("GET", "https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT")
    error = httpx.HTTPStatusError("429 for https://fapi.binance.com/futures/data/openInterestHist", request=request,
                                  response=httpx.Response(429, request=request))
    assert describe_error(error) == "HTTPStatusError (HTTP 429)"
    assert describe_error("no rows returned") == "no rows returned"


def test_a_partial_failure_keeps_the_state_and_a_fetch_counts_its_rows() -> None:
    hb = beat(counts=("fetches", "rows"))
    hb.succeeded(now=T, fetches=1, rows=500)
    hb.error(TimeoutError(), now=T + 5)
    snap = hb.snapshot(now=T + 6)
    assert snap["state"] == "ok" and snap["connected"] and snap["counts_1h"] == {"fetches": 1, "rows": 500}
    assert snap["last_error"] == "TimeoutError" and snap["last_success_at"] < snap["last_error_at"]


def test_a_registry_lists_each_feed_once_in_declared_order() -> None:
    registry = Registry("market-data")
    first = registry.feed("a", label="A", kind="loop", authority="context_only", influence="x")
    assert registry.feed("a", label="ignored", kind="loop", authority="context_only", influence="y") is first
    registry.feed("b", label="B", kind="fetch", authority="context_only", influence="z")
    snap = registry.snapshot(now=T)
    assert [f["id"] for f in snap["feeds"]] == ["a", "b"] and snap["feeds"][0]["label"] == "A"
    assert snap["service"] == "market-data" and snap["window_seconds"] == 3600 and snap["counting_since"]
