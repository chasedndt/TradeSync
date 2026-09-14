"""Adoption and revert change the active paper rulebook together, and revert walks back one adoption."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from tradesync_core.regime_weights import load_rulebook, validate_rulebook

from app import rulebook_activation as activation

ROOT = Path(__file__).resolve().parents[3]
BASELINE = load_rulebook(ROOT / "config" / "regime" / "regime-rulebook-v1.json")


def learned(version, cvd):
    data = json.loads(json.dumps(BASELINE.data))
    data["version"] = version
    data["feature_weights"] = {"hl_direct_cvd": cvd}
    return validate_rulebook(data)


A = learned("1.0.0-learn.a", 1.2)
B = learned("1.0.0-learn.b", 1.44)


def active_row(rulebook, activation_id="act-1", row_id="row-1"):
    return {"activation_id": activation_id, "activated_at": None, "activated_by": "chase",
            "approval_reference": "learning_proposal:p-1", "rulebook_row_id": row_id,
            "config": json.dumps(rulebook.data), "config_digest": rulebook.digest, "version": rulebook.version}


def proposal(rulebook, parent, proposal_id="p-2"):
    return {"id": proposal_id, "parent_digest": parent.digest, "parent_version": parent.version,
            "config": rulebook.data}


class Conn:
    def __init__(self, active=None, adopting=None, parent=None):
        self.active, self.adopting, self.parent = active, adopting, parent
        self.executed: list[tuple[str, tuple]] = []
        self.opened: list[tuple] = []

    async def fetchrow(self, sql, *args):
        if "FROM regime_weight_activations a" in sql and "deactivated_at IS NULL" in sql:
            return self.active
        if "INSERT INTO regime_rulebooks" in sql:
            return {"id": "row-new"}
        if "FROM learning_proposals WHERE config_digest" in sql:
            return self.adopting
        if "FROM regime_rulebooks WHERE config_digest" in sql:
            return self.parent
        raise AssertionError(f"unexpected query: {sql}")

    async def fetchval(self, sql, *args):
        assert "INSERT INTO regime_weight_activations" in sql
        self.opened.append(args)
        return "act-new"

    async def execute(self, sql, *args):
        self.executed.append((" ".join(sql.split()), args))

    def ran(self, fragment):
        return [args for sql, args in self.executed if fragment in sql]


def test_without_an_activation_the_file_is_active() -> None:
    current = asyncio.run(activation.read_active(Conn(), BASELINE))
    assert current.source == "file" and current.rulebook.digest == BASELINE.digest


def test_an_activation_names_the_adopted_rulebook() -> None:
    current = asyncio.run(activation.read_active(Conn(active=active_row(A)), BASELINE))
    assert current.source == "database" and current.rulebook.digest == A.digest
    assert current.summary()["feature_weights"] == {"hl_direct_cvd": 1.2}


def test_an_invalid_activation_falls_back_to_the_file_and_says_so() -> None:
    broken = active_row(A)
    broken["config"] = json.dumps({**A.data, "environment": "live"})
    current = asyncio.run(activation.read_active(Conn(active=broken), BASELINE))
    assert current.source == "file" and "invalid" in current.reason


def test_adopting_over_the_file_opens_one_activation_and_marks_the_proposal() -> None:
    conn = Conn()
    result = asyncio.run(activation.adopt(conn, proposal(A, BASELINE), BASELINE, "chase", "trust CVD more"))
    assert result == {"activation_id": "act-new", "version": A.version, "digest": A.digest}
    assert conn.opened == [("row-new", A.data["horizon"], "chase", "learning_proposal:p-2")]
    assert conn.ran("SET status = 'adopted'")[0][:3] == ("p-2", "chase", "trust CVD more")
    assert not conn.ran("SET deactivated_at = now()")


def test_adopting_over_a_learned_rulebook_closes_it_first() -> None:
    conn = Conn(active=active_row(A))
    asyncio.run(activation.adopt(conn, proposal(B, A), BASELINE, "chase", ""))
    assert conn.ran("SET deactivated_at = now()") == [("act-1",)]
    assert conn.ran("SET status = 'retired'") == [("row-1",)]


def test_a_proposal_built_on_another_rulebook_is_refused() -> None:
    conn = Conn(active=active_row(A))
    with pytest.raises(activation.ActivationConflict):
        asyncio.run(activation.adopt(conn, proposal(B, BASELINE), BASELINE, "chase", ""))
    assert not conn.opened and not conn.executed


def test_there_is_nothing_to_revert_while_the_file_is_active() -> None:
    with pytest.raises(activation.ActivationConflict):
        asyncio.run(activation.revert(Conn(), BASELINE, "chase", ""))


def test_reverting_the_first_adoption_returns_to_the_file() -> None:
    conn = Conn(active=active_row(A), adopting={"id": "p-1", "parent_digest": BASELINE.digest})
    result = asyncio.run(activation.revert(conn, BASELINE, "chase", "worse live"))
    assert result["source"] == "file" and result["digest"] == BASELINE.digest
    assert conn.ran("SET deactivated_at = now()") == [("act-1",)]
    assert conn.ran("SET reverted_at = now()") == [("p-1", "chase")]
    assert not conn.opened


def test_reverting_a_later_adoption_reactivates_its_parent() -> None:
    parent_row = {"id": "row-a", "config": json.dumps(A.data), "version": A.version}
    conn = Conn(active=active_row(B, "act-2", "row-b"), adopting={"id": "p-2", "parent_digest": A.digest}, parent=parent_row)
    result = asyncio.run(activation.revert(conn, BASELINE, "chase", ""))
    assert result["source"] == "database" and result["version"] == A.version
    assert conn.opened == [("row-a", A.data["horizon"], "chase", "revert:act-2")]
    assert conn.ran("SET status = 'paper_active'") == [("row-a",)]
