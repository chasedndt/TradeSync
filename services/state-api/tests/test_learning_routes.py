"""Learning routes read attributions and proposals; adopt, reject and revert need a decision."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests"))
from learning_fixtures import stored_decision  # noqa: E402

from tradesync_core.attribution import MeasuredHorizon, attribute_outcome  # noqa: E402
from tradesync_core.outcome_classification import FAILURES  # noqa: E402

from app import background  # noqa: E402
from app import learning_job as job  # noqa: E402
from app import rulebook_activation as activation  # noqa: E402
from app.learning_routes import NOT_MIGRATED  # noqa: E402
from app.main import app, regime_lab_engine, state  # noqa: E402

client = TestClient(app)
AT = datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc)
PROPOSAL_ID = "11111111-2222-3333-4444-555555555555"
OPPORTUNITY_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class UndefinedTableError(Exception):
    """Named like asyncpg's, which is how the routes recognise it."""


class _Null:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class Conn:
    def __init__(self, fetch=None, fetchrow=None, fetchval=None, error=None):
        self._fetch, self._fetchrow, self._fetchval, self.error = fetch, fetchrow, fetchval, error
        self.calls: list[tuple[str, str, tuple]] = []

    async def _answer(self, kind, handler, sql, args):
        self.calls.append((kind, " ".join(sql.split()), args))
        if self.error:
            raise self.error
        return handler(" ".join(sql.split()), args) if callable(handler) else handler

    async def fetch(self, sql, *args):
        return await self._answer("fetch", self._fetch or [], sql, args)

    async def fetchrow(self, sql, *args):
        return await self._answer("fetchrow", self._fetchrow, sql, args)

    async def fetchval(self, sql, *args):
        return await self._answer("fetchval", self._fetchval, sql, args)

    async def execute(self, sql, *args):
        self.calls.append(("execute", sql, args))

    def transaction(self):
        return _Null()


class Pool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        conn = self.conn

        class Acquire(_Null):
            async def __aenter__(self):
                return conn

        return Acquire()


@pytest.fixture(autouse=True)
def _restore_pool():
    before = state.pool
    yield
    state.pool = before


def use(conn):
    state.pool = Pool(conn)
    return conn


def attribution_db_row(signed=-0.4, horizon=60):
    a = attribute_outcome(opportunity_id=OPPORTUNITY_ID, symbol="BTC-PERP", direction="LONG",
                          opened_at_s=int(AT.timestamp()), decision=stored_decision(),
                          measured=MeasuredHorizon(horizon, signed, 0.05, 0.5), entry_regime="rising").to_dict()
    return {**{k: v for k, v in a.items() if k not in ("won", "decided", "opened_at_s")},
            "opened_at": AT, "features": json.dumps(a["features"]), "blocks": json.dumps(a["blocks"]),
            "outcome_measured_at": AT, "attributed_at": AT}


def test_the_learning_loop_is_registered() -> None:
    assert "opportunity_learning" in background.registered()


def test_the_scoreboard_is_net_of_costs_by_horizon() -> None:
    use(Conn(fetch=[attribution_db_row(0.5), attribution_db_row(-0.4)]))
    body = client.get("/state/learning/scoreboard?days=7").json()
    assert body["attributions"] == 2 and body["horizons"][0]["wins"] == 1
    assert body["cost_pct"] == job.COST_PCT


def test_failures_are_newest_first_and_carry_their_reason() -> None:
    conn = use(Conn(fetch=[attribution_db_row()]))
    body = client.get("/state/learning/failures?horizon=60&limit=5").json()
    assert conn.calls[0][2] == (sorted(FAILURES), 60, 5)
    failure = body["failures"][0]
    assert failure["classification"] == "wrong_direction" and failure["reason"].startswith("BTC LONG")
    assert isinstance(failure["features"], list) and failure["opened_at"].startswith("2026-09-14")


def test_verdicts_cover_every_dimension_for_one_horizon() -> None:
    use(Conn(fetch=[attribution_db_row()]))
    body = client.get("/state/learning/verdicts?horizon=60").json()
    assert {"feature", "block", "regime", "symbol", "horizon"} <= set(body)
    assert body["policy"]["min_decided"] == 50


def test_proposals_are_decoded_from_storage() -> None:
    row = {"id": PROPOSAL_ID, "status": "proposed", "config": json.dumps({"version": "v"}), "weights": "{}",
           "evidence": json.dumps({"window": {}}), "replay": json.dumps({"assessment": "mixed"}), "created_at": AT}
    use(Conn(fetch=[row]))
    proposal = client.get("/state/learning/proposals").json()["proposals"][0]
    assert proposal["replay"] == {"assessment": "mixed"} and proposal["created_at"].startswith("2026-09-14")


def test_the_active_rulebook_and_whether_the_scorer_uses_it() -> None:
    baseline = regime_lab_engine.baseline

    def fetchrow(sql, args):
        if "FROM signals" in sql:
            return {"created_at": AT, "version": baseline.version, "digest": baseline.digest}
        return None

    use(Conn(fetch=[], fetchrow=fetchrow))
    body = client.get("/state/learning/active").json()
    assert body["active"]["source"] == "file" and body["scorer_in_step"] is True


def test_an_opportunitys_own_outcomes_and_attribution() -> None:
    def fetch(sql, args):
        if "FROM opportunity_outcomes" in sql:
            return [{"horizon_minutes": 60, "status": "measured", "entry_price": 1.0, "exit_price": 0.996,
                     "forward_return_pct": -0.4, "signed_return_pct": -0.4, "max_favourable_pct": 0.05,
                     "max_adverse_pct": 0.5, "reason": "", "measured_at": AT}]
        return [attribution_db_row()]

    use(Conn(fetch=fetch, fetchrow={"regime": "rising", "trailing_return_pct": 0.3}))
    body = client.get(f"/state/opportunities/{OPPORTUNITY_ID}/attribution").json()
    assert body["outcomes"][0]["horizon_minutes"] == 60 and body["entry_regime"]["regime"] == "rising"
    assert body["attributions"][0]["classification"] == "wrong_direction"
    assert client.get("/state/opportunities/not-an-id/attribution").status_code == 422


def test_learning_says_when_its_tables_are_not_migrated() -> None:
    use(Conn(error=UndefinedTableError("relation opportunity_attributions does not exist")))
    response = client.get("/state/learning/scoreboard")
    assert response.status_code == 503 and response.json()["detail"] == NOT_MIGRATED


def proposal_row(status="proposed"):
    return {"id": PROPOSAL_ID, "status": status, "parent_digest": "d", "parent_version": "1.0.0",
            "config": "{}", "weights": "{}", "evidence": "{}", "replay": "{}", "created_at": AT}


DECISION = {"decided_by": "chase", "note": "walk-forward favours it", "confirm": True}


def test_adoption_must_be_confirmed() -> None:
    use(Conn())
    response = client.post(f"/state/learning/proposals/{PROPOSAL_ID}/adopt", json={**DECISION, "confirm": False})
    assert response.status_code == 400


def test_adoption_records_the_decision(monkeypatch) -> None:
    seen = {}

    async def adopt(conn, proposal, baseline, decided_by, note):
        seen.update(proposal=proposal["id"], decided_by=decided_by, note=note)
        return {"activation_id": "act-1", "version": "1.0.0-learn.x", "digest": "abc"}

    monkeypatch.setattr(activation, "adopt", adopt)
    use(Conn(fetchrow=proposal_row()))
    response = client.post(f"/state/learning/proposals/{PROPOSAL_ID}/adopt", json=DECISION)
    assert response.status_code == 200 and response.json()["adopted"] is True
    assert seen == {"proposal": PROPOSAL_ID, "decided_by": "chase", "note": "walk-forward favours it"}


@pytest.mark.parametrize("row, status", [(None, 404), (proposal_row("rejected"), 409)])
def test_only_an_open_proposal_can_be_adopted(row, status) -> None:
    use(Conn(fetchrow=row))
    assert client.post(f"/state/learning/proposals/{PROPOSAL_ID}/adopt", json=DECISION).status_code == status


def test_a_stale_proposal_is_refused(monkeypatch) -> None:
    async def adopt(*args):
        raise activation.ActivationConflict("proposal was built on 1.0.0 but 1.0.0-learn.a is active")

    monkeypatch.setattr(activation, "adopt", adopt)
    use(Conn(fetchrow=proposal_row()))
    response = client.post(f"/state/learning/proposals/{PROPOSAL_ID}/adopt", json=DECISION)
    assert response.status_code == 409 and "is active" in response.json()["detail"]


@pytest.mark.parametrize("fetchval, status", [(PROPOSAL_ID, 200), ([None, "adopted"], 409), ([None, None], 404)])
def test_rejection(fetchval, status) -> None:
    answers = list(fetchval) if isinstance(fetchval, list) else [fetchval]
    use(Conn(fetchval=lambda sql, args: answers.pop(0)))
    response = client.post(f"/state/learning/proposals/{PROPOSAL_ID}/reject", json=DECISION)
    assert response.status_code == status


def test_revert_must_be_confirmed_and_reports_conflicts(monkeypatch) -> None:
    use(Conn())
    assert client.post("/state/learning/active/revert", json={**DECISION, "confirm": False}).status_code == 400

    async def revert(*args):
        raise activation.ActivationConflict("the rulebook file is already in use; there is nothing to revert")

    monkeypatch.setattr(activation, "revert", revert)
    assert client.post("/state/learning/active/revert", json=DECISION).status_code == 409


def test_generate_runs_one_proposal_pass(monkeypatch) -> None:
    async def run(pool, baseline, horizon, created_by):
        return {"proposal_id": None, "reason": "no verdict", "horizon_minutes": horizon, "decisions": 0}

    monkeypatch.setattr(job, "run_proposal_pass", run)
    use(Conn())
    assert client.post("/state/learning/proposals/generate", json={"requested_by": "chase", "horizon_minutes": 45}).status_code == 422
    body = client.post("/state/learning/proposals/generate", json={"requested_by": "chase", "horizon_minutes": 60}).json()
    assert body["reason"] == "no verdict" and job.last_runs["proposal"]["requested_by"] == "chase"
