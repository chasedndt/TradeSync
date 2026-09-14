"""The paper scorer decides with the operator-adopted rulebook each cycle, and the file weights otherwise."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _service_import import load_service_module  # noqa: E402

from tradesync_core.market_features import load_catalog  # noqa: E402
from tradesync_core.regime_weights import load_rulebook, validate_rulebook  # noqa: E402
from tradesync_core.rulebook_evidence import evaluate_rulebook_evidence  # noqa: E402

_weights = load_service_module("core_scorer_app", "core-scorer", "active_weights")
_cycle = load_service_module("core_scorer_app", "core-scorer", "regime_cycle")
_source = load_service_module("core_scorer_app", "core-scorer", "regime_source")

ROOT = Path(__file__).resolve().parents[1]
CATALOG = load_catalog(ROOT / "config" / "features" / "market-feature-catalog-v1.json")
FILE_RULEBOOK = load_rulebook(ROOT / "config" / "regime" / "regime-rulebook-v1.json")


def results():
    now = int(time.time() * 1000)
    return [
        {"feature_id": "hl_return_1h_pct", "block": "price_volatility", "score": 0.4, "data_quality": 1.0,
         "scoring_allowed": True, "provenance": "derived", "observed_at_ms": now},
        {"feature_id": "hl_direct_cvd", "block": "price_volatility", "score": -0.3, "data_quality": 1.0,
         "scoring_allowed": True, "provenance": "observed", "observed_at_ms": now},
        {"feature_id": "hl_spread_bps", "block": "liquidity", "score": -0.2, "data_quality": 1.0,
         "scoring_allowed": True, "provenance": "derived", "observed_at_ms": now},
    ]


def evidence(readings):
    evaluation, directional = evaluate_rulebook_evidence(CATALOG, FILE_RULEBOOK, readings)
    return _source.RegimeEvidence(
        available=True, evaluation=evaluation, feature_results=list(readings),
        catalog={"catalog_id": CATALOG.data["catalog_id"], "version": CATALOG.version, "digest": CATALOG.digest},
        directional=directional, source_status={"status": "live"},
    )


def adopted(weights):
    data = json.loads(json.dumps(FILE_RULEBOOK.data))
    data["feature_weights"] = weights
    data["version"] = "1.0.0-learn.test"
    return validate_rulebook(data)


class FakeConn:
    def __init__(self, row=None, error=None):
        self.row, self.error, self.queries = row, error, []

    async def fetchrow(self, sql, *args):
        self.queries.append((sql, args))
        if self.error:
            raise self.error
        return self.row

    async def close(self):
        return None


def run(conn, ev):
    return asyncio.run(_weights.apply_active_rulebook(conn, ev))


def test_without_an_adopted_rulebook_the_file_weights_stand() -> None:
    ev = evidence(results())
    out, choice = run(FakeConn(), ev)
    assert out is ev
    assert choice.source == "file" and not choice.fell_back


def test_an_adopted_rulebook_reweights_the_same_readings() -> None:
    rulebook = adopted({"hl_return_1h_pct": 3.0})
    readings = results()
    conn = FakeConn({"config": json.dumps(rulebook.data), "version": rulebook.version})
    out, choice = run(conn, evidence(readings))
    assert choice.source == "database" and choice.version == rulebook.version
    assert out.evaluation["config_digest"] == rulebook.digest
    assert out.directional["score"] == pytest.approx((3 * 0.4 - 0.3) / 4)
    assert out.feature_results == readings
    assert conn.queries[0][1] == ("tradesync-intraday-regime",)


def test_an_invalid_adopted_rulebook_falls_back_to_the_file() -> None:
    bad = json.loads(json.dumps(FILE_RULEBOOK.data))
    bad["blocks"]["liquidity"]["weight"] = 0.9
    ev = evidence(results())
    out, choice = run(FakeConn({"config": bad, "version": "bad"}), ev)
    assert out is ev and choice.fell_back and "invalid" in choice.reason


def test_a_catalog_mismatch_falls_back_to_the_file() -> None:
    rulebook = adopted({"hl_return_1h_pct": 3.0})
    ev = replace(evidence(results()), catalog={"digest": "a-different-catalog"})
    out, choice = run(FakeConn({"config": rulebook.data, "version": rulebook.version}), ev)
    assert out is ev and choice.fell_back and "catalog" in choice.reason


def test_an_unreadable_database_falls_back_to_the_file() -> None:
    ev = evidence(results())
    out, choice = run(FakeConn(error=RuntimeError("connection lost")), ev)
    assert out is ev and choice.fell_back and "unreadable" in choice.reason


@pytest.mark.parametrize("adopt, expected", [(False, (False, "NONE")), (True, (True, "LONG"))])
def test_the_cycle_decides_with_whatever_is_active(monkeypatch, adopt, expected) -> None:
    rulebook = adopted({"hl_return_1h_pct": 3.0})
    row = {"config": json.dumps(rulebook.data), "version": rulebook.version} if adopt else None
    conn = FakeConn(row)
    ev = evidence(results())
    captured = {}

    async def connect(dsn):
        return conn

    async def fetch(symbol):
        return ev

    async def last_direction(conn, symbol, max_age):
        return None

    async def persist(conn, decision):
        captured["decision"] = decision
        return "signal-1", None

    async def active_opportunity(conn, symbol, direction):
        return True  # treated as a duplicate, so nothing is published

    monkeypatch.setattr(_cycle.asyncpg, "connect", connect)
    monkeypatch.setattr(_cycle, "fetch_regime_evidence", fetch)
    monkeypatch.setattr(_cycle, "last_admitted_direction", last_direction)
    monkeypatch.setattr(_cycle, "persist_decision", persist)
    monkeypatch.setattr(_cycle, "has_active_opportunity", active_opportunity)
    asyncio.run(_cycle.record_symbol_verdict("BTC-PERP"))

    decision = captured["decision"]
    assert (decision.admitted, decision.direction) == expected
    expected_digest = rulebook.digest if adopt else FILE_RULEBOOK.digest
    assert decision.evidence["rulebook_digest"] == expected_digest
