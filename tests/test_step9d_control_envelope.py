from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "libs" / "tradesync_core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from tradesync_core.control_envelope import (
    ApprovalConsumptionStore,
    ControlEnvelopeError,
    build_paper_control_envelope,
    validate_paper_control_envelope,
)
from tradesync_core.paper_ledger import PaperLedger, evaluate_approved_envelope


def candidate() -> dict:
    return {
        "schema_version": "trade_candidate_v1",
        "candidate_id": "cand_bridge_001",
        "created_at_utc": "2026-08-17T09:00:00Z",
        "valid_from_utc": "2026-08-17T09:00:00Z",
        "evidence_cutoff_utc": "2026-08-17T09:00:00Z",
        "expires_at_utc": "2026-08-17T10:00:00Z",
        "candidate": {"status": "review_only", "direction": "long", "candidate_type": "directional"},
        "instrument": {"asset": "BTC", "canonical_symbol": "BTC-USD-PERP", "market_type": "perpetual", "venue_preference": "hyperliquid"},
        "activation": {"operator": "all", "conditions": [{"field": "close", "operator": "above", "value": 65000}]},
        "invalidation": {"operator": "any", "conditions": [{"field": "close", "operator": "below", "value": 64200}]},
        "lineage": {"signal_ids": ["sig_001"], "scenario_ids": ["scn_001"], "source_item_ids": ["src_001"]},
        "risk": {"risk_status": "not_evaluated", "requested_size": None, "requested_leverage": None, "approved_size": None, "approved_leverage": None, "risk_decision_id": None},
        "execution": {"execution_gateway_status": "disabled", "live_execution_allowed": False, "order_creation_allowed": False, "paper_execution_allowed": False, "order_id": None},
        "governance": {"authority_level": "level_0_observation_only", "operator_approval_status": "not_requested", "self_authority_change_allowed": False},
    }


def envelope() -> dict:
    return build_paper_control_envelope(
        candidate(), approval_id="task-sz-001", approval_digest="a" * 64,
        approval_decision_id="event-001", approved_at_utc="2026-08-17T09:05:00Z",
    )


def test_builds_tamper_evident_single_use_paper_envelope() -> None:
    result = envelope()
    assert result["envelope_id"].startswith("tce_")
    assert result["venue"] == "hyperliquid"
    assert result["approval"]["scope"] == "once"
    assert result["approval"]["authorizes"] == "paper_evaluation_only"
    assert result["authority"]["live_execution_authorized"] is False
    assert result["authority"]["wallet_authorized"] is False


@pytest.mark.parametrize("field", ["live_execution_authorized", "wallet_authorized", "credential_access_authorized"])
def test_rejects_any_authority_expansion(field: str) -> None:
    unsafe = envelope()
    unsafe["authority"][field] = True
    with pytest.raises(ControlEnvelopeError, match="closed authority") as exc:
        validate_paper_control_envelope(unsafe)
    assert exc.value.code == "authority_invariant_violation"


def test_rejects_candidate_tampering_after_approval() -> None:
    tampered = envelope()
    tampered["candidate"]["candidate"]["direction"] = "short"
    with pytest.raises(ControlEnvelopeError) as exc:
        validate_paper_control_envelope(tampered)
    assert exc.value.code == "candidate_integrity_failure"


def test_rejects_live_capability_smuggled_in_candidate() -> None:
    unsafe_candidate = candidate()
    unsafe_candidate["execution"]["live_execution_allowed"] = True
    with pytest.raises(ControlEnvelopeError) as exc:
        build_paper_control_envelope(
            unsafe_candidate, approval_id="task-sz-001", approval_digest="a" * 64,
            approval_decision_id="event-001", approved_at_utc="2026-08-17T09:05:00Z",
        )
    assert exc.value.code == "authority_invariant_violation"


def test_rejects_approval_after_candidate_expiry() -> None:
    with pytest.raises(ControlEnvelopeError) as exc:
        build_paper_control_envelope(
            candidate(), approval_id="task-sz-001", approval_digest="a" * 64,
            approval_decision_id="event-001", approved_at_utc="2026-08-17T10:05:00Z",
        )
    assert exc.value.code == "approval_after_expiry"


def test_rejects_envelope_identity_tampering() -> None:
    tampered = deepcopy(envelope())
    tampered["approval"]["approval_decision_id"] = "event-002"
    with pytest.raises(ControlEnvelopeError) as exc:
        validate_paper_control_envelope(tampered)
    assert exc.value.code == "envelope_integrity_failure"


def test_rejects_non_sha256_approval_digest() -> None:
    with pytest.raises(ControlEnvelopeError) as exc:
        build_paper_control_envelope(
            candidate(), approval_id="task-sz-001", approval_digest="not-a-digest",
            approval_decision_id="event-001", approved_at_utc="2026-08-17T09:05:00Z",
        )
    assert exc.value.code == "invalid_approval"


def test_consumes_a_paper_approval_once_durably(tmp_path: Path) -> None:
    store = ApprovalConsumptionStore(tmp_path / "authority" / "consumption.sqlite3")
    first = store.consume(envelope(), consumed_at_utc="2026-08-17T09:06:00Z")
    assert first["approval_id"] == "task-sz-001"
    with pytest.raises(ControlEnvelopeError) as exc:
        store.consume(envelope(), consumed_at_utc="2026-08-17T09:07:00Z")
    assert exc.value.code == "approval_already_consumed"


def test_concurrent_consumers_allow_exactly_one(tmp_path: Path) -> None:
    store = ApprovalConsumptionStore(tmp_path / "consumption.sqlite3")

    def attempt() -> str:
        try:
            store.consume(envelope(), consumed_at_utc="2026-08-17T09:06:00Z")
            return "consumed"
        except ControlEnvelopeError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=12) as pool:
        outcomes = list(pool.map(lambda _: attempt(), range(24)))
    assert outcomes.count("consumed") == 1
    assert set(outcomes) <= {"consumed", "approval_already_consumed", "approval_consumption_conflict"}


def test_conflicting_alias_of_a_consumed_decision_is_denied(tmp_path: Path) -> None:
    store = ApprovalConsumptionStore(tmp_path / "consumption.sqlite3")
    store.consume(envelope(), consumed_at_utc="2026-08-17T09:06:00Z")
    alias = build_paper_control_envelope(
        candidate(), approval_id="different-id", approval_digest="b" * 64,
        approval_decision_id="event-001", approved_at_utc="2026-08-17T09:05:00Z",
    )
    with pytest.raises(ControlEnvelopeError) as exc:
        store.consume(alias, consumed_at_utc="2026-08-17T09:07:00Z")
    assert exc.value.code == "approval_binding_conflict"


def test_expired_approval_is_not_consumed(tmp_path: Path) -> None:
    store = ApprovalConsumptionStore(tmp_path / "consumption.sqlite3")
    with pytest.raises(ControlEnvelopeError) as exc:
        store.consume(envelope(), consumed_at_utc="2026-08-17T10:00:01Z")
    assert exc.value.code == "approval_expired"


def test_approved_bridge_consumes_before_paper_evaluation(tmp_path: Path) -> None:
    result = evaluate_approved_envelope(
        envelope(),
        [{"closed_at_utc": "2026-08-17T09:10:00Z", "close": 65050}],
        paper_ledger=PaperLedger(tmp_path / "paper.jsonl"),
        consumption_store=ApprovalConsumptionStore(tmp_path / "consumption.sqlite3"),
        consumed_at_utc="2026-08-17T09:06:00Z",
    )
    assert result["paper_result"]["status"] == "paper_filled"
    assert result["live_order_created"] is False
    assert result["wallet_action_performed"] is False
    assert result["credential_accessed"] is False
