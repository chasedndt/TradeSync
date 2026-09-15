"""Managed paper routes over fake storage and market data.

Universe eligibility from the API, entry evidence cut off at the entry time with a
verifiable digest, settled funding stored once and netted out, late settlements for a
closed position, the rules catalog and entry admission.
"""

import asyncio
import json
import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import managed_paper, paper_funding_store
from paper_fakes import H, SYMBOL, UNIVERSE, FakeConn, FakeMarket, book, hourly_candles, market_routes, pool_of, utc
from tradesync_core import paper_entry_evidence
from tradesync_core.managed_paper import advance, open_position
from tradesync_core.paper_lifecycle_rules import LIFECYCLE_VERSION


def build(conn):
    app = FastAPI()
    handles = managed_paper.register(app, SimpleNamespace(pool=pool_of(conn)), market_data_url="http://market-data")
    return TestClient(app), handles


@pytest.fixture
def market():
    FakeMarket.routes = market_routes()
    FakeMarket.requested = []
    with patch("httpx.AsyncClient", FakeMarket):
        yield FakeMarket


def opportunity(**overrides):
    now = time.time()
    signal = uuid.uuid4()
    return {"id": uuid.uuid4(), "symbol": SYMBOL, "dir": "SHORT", "timeframe": "1m", "snapshot_ts": utc(now - 30),
            "expires_at": utc(now + 870), "bias": -0.3, "quality": 55.0, "status": "new", "signal_id": signal,
            "links": {"signal_id": str(signal), "evidence_digest": "e" * 64}, "confluence": {}, **overrides}


def entry_handlers(opp, *, paused=False, active=()):
    now = time.time()
    verdict = {"admitted": True, "direction": "SHORT", "weighted_score": -0.28, "directional_score": -0.27, "data_coverage": 0.54,
               "rejection_reasons": [], "evidence": {"evaluated_at_ms": int((now - 31) * 1000), "catalog_version": "1.8.0"},
               "contributing_features": [{"feature_id": "hl_direct_cvd", "block": "price_volatility", "score": -0.3,
                                          "observed_at_ms": int((now - 40) * 1000)}]}
    minute = now // 60 * 60
    return [
        ("SELECT id FROM managed_paper_positions WHERE opportunity_id", None),
        ("SELECT * FROM opportunities", opp),
        ("FROM signals", {"id": opp["signal_id"], "created_at": utc(now - 30), "agent": "regime_paper_scorer",
                          "kind": "regime_paper_signal", "confidence": 0.7, "dir": "SHORT", "features": verdict}),
        ("FROM market_depth_snapshots", {"observed_at": utc(minute - 60), "recorded_at": utc(now - 50), "mid_price": 50.0,
                                         "bids": [[49.9, 300.0], [49.8, 500.0]], "asks": [[50.1, 200.0], [50.2, 900.0]]}),
        ("FROM market_liquidation_events", []),
        ("FROM market_open_interest", {"observed_at": utc(minute - 60), "recorded_at": utc(now - 45), "open_interest_usd": 1.2e9,
                                       "mark_price": 50.0, "oracle_price": 50.02, "funding_rate": 1.25e-05,
                                       "oracle_premium_bps": -3.0, "volume_24h_usd": 5e8}),
        ("FROM thesis_editions", {"id": uuid.uuid4(), "edition": "session-handoff", "generated_at": utc(now - 3 * H),
                                  "trigger": "schedule", "headline": "MIXED", "verdicts": {SYMBOL: "NO TRADE"},
                                  "schema_version": "thesis_edition_v1"}),
        ("SELECT entries_paused", paused),
        ("position_state->>'status'='open'", list(active)),
    ]


def post_entry(client, opp, style="intraday"):
    return client.post("/state/paper-positions", json={"opportunity_id": str(opp["id"]), "style": style, "notional": 250})


def test_entry_freezes_evidence_cut_off_at_entry_with_a_verifiable_digest(market):
    opp = opportunity()
    conn = FakeConn(entry_handlers(opp))
    client, _ = build(conn)
    started = time.time()
    risk_gate = AsyncMock()  # the paper risk engine's admission; tests/test_paper_risk_gate.py covers its refusals
    with patch("app.managed_paper.admit_entry", risk_gate):
        response = post_entry(client, opp)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["duplicate"] is False and body["execution_authority"] is False
    (_identity, _opportunity, symbol, stored, digest, plan_text), = conn.statements("INSERT INTO managed_paper_positions")
    document = json.loads(stored)
    assert symbol == SYMBOL and digest == body["evidence_sha256"] == paper_entry_evidence.digest(document)
    entry = document["entry_time"]
    assert document["schema_version"] == paper_entry_evidence.SCHEMA_VERSION and started <= entry <= time.time()
    items = document["items"]
    assert document["item_order"] == [key for key, _ in paper_entry_evidence.ITEMS] and set(items) == set(document["item_order"])
    # A feature the venue stamped after the entry instant is excluded, with its reason.
    assert [r["feature_id"] for r in items["features"]["records"]] == ["hl_spread_bps"]
    assert [e["reason"] for e in items["features"]["excluded"]] == ["observed after entry"]
    for item in items.values():
        assert all(r["observed_at"] <= entry and r["received_at"] <= entry and r["age_s"] >= 0 for r in item["records"])
    assert items["horizon_measurement"]["status"] == "missing" and "503" in items["horizon_measurement"]["reason"]
    assert items["liquidations"]["reason"] == "no liquidation received in the hour before entry"
    assert [r["id"] for r in items["resting_liquidity"]["records"]] == ["recorded_book", "entry_book"]
    assert items["resting_liquidity"]["records"][0]["walls"]["below"]["price"] == 49.8
    assert items["scorer_verdict"]["records"][0]["admitted"] is True
    assert items["thesis_edition"]["records"][0]["verdict"] == "NO TRADE"
    assert [r["reading"] for r in items["open_interest"]["records"]] == ["latest", "an hour earlier"]
    assert len(items["funding"]["records"]) == 3
    assert document["external_context"]["bybit_liquidations"]["status"] == "no_eligible_receipts"
    # Every evidence request completed before the entry book was requested.
    depth_at = next(i for i, url in enumerate(FakeMarket.requested) if "/depth/" in url)
    assert all(not any(n in url for n in ("/features/", "/funding-history/", "/liquidation-context/", "/book-history/", "/horizons"))
               for url in FakeMarket.requested[depth_at:])
    plan = json.loads(plan_text)
    assert risk_gate.await_args.kwargs == {"symbol": SYMBOL, "plan": plan}
    assert plan["version"] == LIFECYCLE_VERSION and plan["side"] == "short" and plan["rules"]["style"] == "intraday"
    assert plan["slippage"]["entry"]["snapshot"]["source"] == "hyperliquid_l2_book"
    assert plan["planning"]["funding"]["rows"] == 3 and plan["fees"]["rate"] == 0.00045
    assert [args[2] for args in conn.statements("INSERT INTO managed_paper_events")] == ["opened"]


def test_symbols_outside_the_api_universe_are_refused_before_any_book(market):
    opp = opportunity(symbol="DOGE-PERP")
    client, _ = build(FakeConn(entry_handlers(opp)))
    response = post_entry(client, opp)
    assert response.status_code == 422 and "not in the tracked symbol universe" in response.text
    assert not any("/depth/" in url for url in FakeMarket.requested)


def test_an_unreadable_universe_admits_nothing(market):
    FakeMarket.routes = [("/snapshots", lambda url, params: (500, {}))] + market_routes()
    opp = opportunity()
    client, _ = build(FakeConn(entry_handlers(opp)))
    assert post_entry(client, opp).status_code == 503


def test_a_failed_gate_refuses_without_storing(market):
    wide = [(f"/candles/hyperliquid/{SYMBOL}", lambda url, params: (200, hourly_candles(time.time(), half_range=5.0)))]
    FakeMarket.routes = wide + market_routes()
    opp = opportunity()
    conn = FakeConn(entry_handlers(opp))
    client, _ = build(conn)
    response = post_entry(client, opp)
    assert response.status_code == 409 and "Invalid stop distance" in response.text
    assert conn.statements("INSERT INTO managed_paper_positions") == []


def test_candidates_offer_fresh_directional_opportunities_for_the_whole_universe(market):
    now = time.time()
    def row(symbol, direction, age):
        return {"id": uuid.uuid4(), "symbol": symbol, "timeframe": "1m", "dir": direction, "bias": 0.2, "quality": 50.0,
                "snapshot_ts": utc(now - age), "expires_at": utc(now - age + 900), "position_id": None}
    rows = [row(SYMBOL, "SHORT", 40), row("ZEC-PERP", "LONG", 400), row("DOGE-PERP", "LONG", 10), row("BTC-PERP", "NEUTRAL", 20)]
    client, _ = build(FakeConn([("FROM opportunities o LEFT JOIN managed_paper_positions", rows)]))
    body = client.get("/state/paper-positions/candidates").json()
    assert [c["symbol"] for c in body["candidates"]] == [SYMBOL] and body["candidates"][0]["direction"] == "short"
    assert body["universe"] == UNIVERSE and body["symbols_without_candidate"] == ["BTC-PERP", "ZEC-PERP"]


def test_evidence_route_verifies_the_stored_digest():
    document = paper_entry_evidence.document({}, time.time(), inputs={"atr": 1.0})
    row = {"entry_evidence": paper_entry_evidence.canonical_json(document), "evidence_sha256": paper_entry_evidence.digest(document),
           "initial_plan": "{}"}
    client, _ = build(FakeConn([("SELECT entry_evidence", row)]))
    assert client.get(f"/state/paper-positions/{uuid.uuid4()}/evidence").json()["digest_verified"] is True
    client, _ = build(FakeConn([("SELECT entry_evidence", dict(row, entry_evidence=json.dumps({**document, "atr": 2.0})))]))
    assert client.get(f"/state/paper-positions/{uuid.uuid4()}/evidence").json()["digest_verified"] is False


def held_position(now, *, closed_after_s=None):
    entry_time = int(now // H) * H - 2 * H + 600
    plan = open_position("long", "intraday", 250, 0.5, book(entry_time), entry_time)
    if closed_after_s is not None:
        plan = advance(plan, book(entry_time + closed_after_s), entry_time + closed_after_s, manual_close=True)
    return plan


def position_handlers(state):
    return [
        ("SELECT symbol,position_state FROM managed_paper_positions WHERE id", {"symbol": SYMBOL, "position_state": json.dumps(state)}),
        ("SELECT position_state FROM managed_paper_positions WHERE id=$1 FOR UPDATE", {"position_state": json.dumps(state)}),
        ("FROM market_open_interest WHERE symbol=$1 AND observed_at BETWEEN",
         lambda symbol, start, end, hour: {"observed_at": utc(hour - 20), "oracle_price": 50.5, "mark_price": 50.4}),
    ]


def test_observer_stores_each_settlement_once_and_nets_it_out(market):
    plan = held_position(time.time())
    identity = uuid.uuid4()
    conn = FakeConn(position_handlers(plan))
    _, handles = build(conn)
    result = asyncio.run(handles.update(identity))
    assert result["status"] == "open" and result["funding"]["status"] == "complete" and result["funding"]["settled_hours"] == 2
    payments = [row["payment_usdc"] for row in conn.funding]
    assert payments[0] == pytest.approx(plan["quantity"] * 50.5 * 1.25e-05)
    assert result["funding_usdc"] == pytest.approx(sum(payments))
    assert result["net_estimate_usdc"] == pytest.approx(result["gross_pnl_usdc"] - result["fees_usdc"] - result["funding_usdc"])
    (_, _, kind, payload), = conn.statements("INSERT INTO managed_paper_events")
    assert kind == "observed" and json.loads(payload)["funding_rows_added"] == 2
    rates = {row["settled_at"].timestamp(): {"funding_rate": 1.25e-05, "premium": 0.0} for row in conn.funding}
    assert asyncio.run(paper_funding_store.store(conn, identity, SYMBOL, result, rates, time.time(), time.time())) == 0


def test_late_settlements_settle_a_closed_position(market):
    closed = held_position(time.time(), closed_after_s=H)
    assert closed["funding"]["status"] == "awaiting_rows" and len(closed["funding"]["missing_hours"]) == 1
    conn = FakeConn(position_handlers(closed))
    _, handles = build(conn)
    settled = asyncio.run(handles.update(uuid.uuid4()))
    assert settled["funding"]["status"] == "complete" and len(conn.funding) == 1
    assert settled["net_estimate_usdc"] == pytest.approx(closed["net_estimate_usdc"] - conn.funding[0]["payment_usdc"])
    assert [args[2] for args in conn.statements("INSERT INTO managed_paper_events")] == ["funding_settled"]
    assert not any("/depth/" in url for url in FakeMarket.requested)


def test_funding_route_serves_stored_settlements():
    identity = uuid.uuid4()
    conn = FakeConn([("SELECT position_state FROM managed_paper_positions WHERE id", "{}")])
    conn.funding.append({"position_id": identity, "settled_at": utc(10 * H), "funding_rate": 1e-5, "premium": 0.0, "side": "long",
                         "quantity": 2.0, "price": 50.0, "price_source": "market_open_interest.oracle_price",
                         "price_observed_at": utc(10 * H - 20), "payment_usdc": 0.001, "source": "hyperliquid_funding_history",
                         "received_at": utc(10 * H + 30), "recorded_at": utc(10 * H + 31)})
    client, _ = build(conn)
    body = client.get(f"/state/paper-positions/{identity}/funding").json()
    assert body["rows"][0]["settled_at"] == 10 * H and body["rows"][0]["price_observed_at"] == 10 * H - 20
    client, _ = build(FakeConn([("SELECT position_state FROM managed_paper_positions WHERE id", None)]))
    assert client.get(f"/state/paper-positions/{identity}/funding").status_code == 404


def test_rules_catalog_names_versions_and_cost_sources():
    client, _ = build(FakeConn([]))
    body = client.get("/state/paper-positions/rules").json()
    assert body["version"] == LIFECYCLE_VERSION and set(body["styles"]) == {"scalp", "intraday", "swing"}
    assert body["fees"]["taker_fee"] == 0.00045 and body["funding_model"] == "hyperliquid_settled_hourly_v1"
    assert body["evidence_schema"] == paper_entry_evidence.SCHEMA_VERSION and body["authority"] == "paper_only"


def test_admission_refuses_paused_entries_the_portfolio_cap_and_stale_evidence():
    def refused(conn, captured_at):
        with pytest.raises(HTTPException) as caught:
            asyncio.run(managed_paper.entry_admission(conn, SYMBOL, {}, captured_at))
        return caught.value
    risk_gate = AsyncMock()
    with patch("app.managed_paper.admit_entry", risk_gate):
        assert "paused" in refused(FakeConn([("SELECT entries_paused", True)]), time.time()).detail
        risk_gate.assert_not_awaited()  # a paused control refuses before the paper risk engine is asked
        busy = FakeConn([("SELECT entries_paused", False), ("position_state->>'status'='open'", [{"symbol": SYMBOL, "position_state": "{}"}])])
        assert "cap" in refused(busy, time.time()).detail
        quiet = [("SELECT entries_paused", False), ("position_state->>'status'='open'", [])]
        assert "expired" in refused(FakeConn(quiet), time.time() - 31).detail
        assert asyncio.run(managed_paper.entry_admission(FakeConn(quiet), SYMBOL, {}, time.time())) is None
    assert risk_gate.await_count == 3 and risk_gate.await_args.kwargs == {"symbol": SYMBOL, "plan": {}}
    # A risk refusal stops admission before the portfolio is read: this connection has no answer for that query.
    refusal = HTTPException(409, "Paper entry refused [KILL_SWITCH_ACTIVE]: Kill switch engaged by chase: review")
    with patch("app.managed_paper.admit_entry", AsyncMock(side_effect=refusal)):
        assert refused(FakeConn([("SELECT entries_paused", False)]), time.time()) is refusal
