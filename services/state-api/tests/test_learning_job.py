"""The learning job attributes what changed, idempotently, and stores walk-forward proposals."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests"))
from learning_fixtures import stored_decision  # noqa: E402

from tradesync_core.attribution import SCHEMA_VERSION, MeasuredHorizon  # noqa: E402
from tradesync_core.regime_weights import load_rulebook  # noqa: E402
from tradesync_core.walk_forward import DecisionRecord  # noqa: E402

from app import learning_job as job  # noqa: E402
from app import learning_store as store  # noqa: E402
from app import rulebook_activation as activation  # noqa: E402

T0 = datetime(2026, 9, 10, tzinfo=timezone.utc)
BASELINE = load_rulebook(ROOT / "config" / "regime" / "regime-rulebook-v1.json")


class _Null:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class Conn:
    def transaction(self):
        return _Null()


class Pool:
    def __init__(self):
        self.conn = Conn()

    def acquire(self):
        conn = self.conn

        class Acquire(_Null):
            async def __aenter__(self):
                return conn

        return Acquire()


def outcome(i, horizon=60, regime="rising"):
    return {
        "opportunity_id": f"00000000-0000-0000-0000-{i:012d}", "horizon_minutes": horizon, "symbol": "BTC-PERP",
        "direction": "LONG", "opened_at": T0 + timedelta(hours=i),
        "measured_at": T0 + timedelta(hours=i, minutes=horizon + 5), "signed_return_pct": -0.4,
        "max_favourable_pct": 0.05, "max_adverse_pct": 0.5, "confluence": json.dumps(stored_decision()), "regime": regime,
    }


class Database:
    """The candidate predicate of learning_store.CANDIDATES_SQL, over rows held in memory."""

    def __init__(self, outcomes):
        self.outcomes, self.attributions, self.writes = outcomes, {}, 0

    async def candidates(self, conn, cost_pct, batch):
        pending = []
        for row in self.outcomes:
            stored = self.attributions.get((row["opportunity_id"], row["horizon_minutes"]))
            if (stored is None or stored["outcome_measured_at"] < row["measured_at"]
                    or stored["cost_pct"] != cost_pct or stored["schema_version"] != SCHEMA_VERSION
                    or (stored["entry_regime"] == "unknown" and row["regime"] not in (None, "unknown"))):
                pending.append(row)
        return pending[:batch]

    async def upsert(self, conn, attribution, opened_at, measured_at):
        self.writes += 1
        key = (attribution["opportunity_id"], attribution["horizon_minutes"])
        self.attributions[key] = {**attribution, "outcome_measured_at": measured_at}


@pytest.fixture
def database(monkeypatch):
    db = Database([outcome(i, h) for i in range(3) for h in (15, 60)])
    monkeypatch.setattr(store, "attribution_candidates", db.candidates)
    monkeypatch.setattr(store, "upsert_attribution", db.upsert)
    return db


def run_pass(**kwargs):
    return asyncio.run(job.run_attribution_pass(Pool(), **kwargs))


def test_each_decision_is_split_once_across_its_horizons(monkeypatch) -> None:
    calls = []
    real = job.contributions_from_decision
    monkeypatch.setattr(job, "contributions_from_decision", lambda d: calls.append(1) or real(d))
    results, skipped = job.attribute_rows([outcome(0, h) for h in (15, 60, 240)], 0.12)
    assert len(results) == 3 and skipped == 0 and len(calls) == 1
    assert results[0][0]["classification"] == "wrong_direction"


def test_the_pass_is_idempotent_and_picks_up_only_what_changed(database) -> None:
    assert run_pass(cost_pct=0.12)["attributed"] == 6
    assert run_pass(cost_pct=0.12)["attributed"] == 0 and database.writes == 6
    database.outcomes[0]["measured_at"] += timedelta(hours=1)  # re-measured
    assert run_pass(cost_pct=0.12)["attributed"] == 1
    assert run_pass(cost_pct=0.2)["attributed"] == 6  # a new cost re-attributes everything
    assert {a["cost_pct"] for a in database.attributions.values()} == {0.2}


def test_batches_drain_a_backlog(database) -> None:
    stats = run_pass(cost_pct=0.12, batch=4)
    assert stats == {"attributed": 6, "skipped": 0, "batches": 2}


def test_an_entry_regime_that_arrives_later_is_attributed_again(database) -> None:
    database.outcomes[0]["regime"] = None
    run_pass(cost_pct=0.12)
    key = (database.outcomes[0]["opportunity_id"], database.outcomes[0]["horizon_minutes"])
    assert database.attributions[key]["entry_regime"] == "unknown"
    database.outcomes[0]["regime"] = "falling"
    assert run_pass(cost_pct=0.12)["attributed"] == 1
    assert database.attributions[key]["entry_regime"] == "falling"


def test_the_candidate_query_names_every_staleness_condition() -> None:
    sql = " ".join(store.CANDIDATES_SQL.split())
    for condition in ("a.opportunity_id IS NULL", "a.outcome_measured_at < x.measured_at",
                      "a.cost_pct <> $1", "a.schema_version <> $2", "a.entry_regime = 'unknown'"):
        assert condition in sql
    assert "ON CONFLICT (opportunity_id, horizon_minutes) DO UPDATE" in " ".join(store.UPSERT_SQL.split())


def record(i, market_up):
    cvd, ret = (0.7, -0.3) if market_up else (-0.7, 0.3)
    direction = "LONG" if market_up else "SHORT"
    return DecisionRecord(f"opp-{i:04d}", "BTC-PERP", direction, 1_788_800_400 + i * 3600,
                          stored_decision(direction=direction, ret=ret, cvd=cvd, liquidity=False), "rising",
                          {60: MeasuredHorizon(60, 0.5, 0.6, 0.05)})


def proposal_pass(monkeypatch, records):
    inserted = []

    async def read_active(conn, baseline):
        return activation.ActiveRulebook(baseline, "file")

    async def decision_records(conn, days):
        return records

    async def insert_proposal(conn, payload):
        inserted.append(payload)
        return "proposal-1"

    monkeypatch.setattr(activation, "read_active", read_active)
    monkeypatch.setattr(store, "decision_records", decision_records)
    monkeypatch.setattr(store, "insert_proposal", insert_proposal)
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    outcome_ = asyncio.run(job.run_proposal_pass(Pool(), BASELINE, horizon=60, created_by="chase", now=now))
    return outcome_, inserted


def test_a_proposal_pass_without_verdicts_stores_nothing(monkeypatch) -> None:
    result, inserted = proposal_pass(monkeypatch, [record(i, i % 2 == 0) for i in range(20)])
    assert result["proposal_id"] is None and inserted == []
    assert "no feature or block has a verdict" in result["reason"]


def test_a_proposal_pass_stores_the_walk_forward_evidence(monkeypatch) -> None:
    result, inserted = proposal_pass(monkeypatch, [record(i, i % 2 == 0) for i in range(300)])
    assert result["proposal_id"] == "proposal-1"
    payload = inserted[0]
    assert payload["version"] == "1.0.0-learn.202609141200"
    assert payload["parent_digest"] == BASELINE.digest and payload["created_by"] == "chase"
    assert payload["config"]["feature_weights"] == {"hl_direct_cvd": 1.2, "hl_return_1h_pct": 0.8}
    assert payload["replay"]["assessment"] and payload["evidence"]["parent_source"] == "file"
    assert payload["hypothesis"] == payload["config"]["purpose"]
