from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "libs" / "tradesync_core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from tradesync_core.paper_ledger import PaperLedger, PaperLedgerError, execution_blueprint


def candidate() -> dict:
    return {
        "schema_version": "trade_candidate_v1",
        "candidate_id": "cand_step9c_fixture_001",
        "created_at_utc": "2026-07-24T09:00:00Z",
        "valid_from_utc": "2026-07-24T09:00:00Z",
        "evidence_cutoff_utc": "2026-07-24T09:00:00Z",
        "expires_at_utc": "2026-07-24T10:00:00Z",
        "candidate": {
            "status": "review_only",
            "direction": "long",
            "candidate_type": "directional",
        },
        "instrument": {
            "asset": "BTC",
            "canonical_symbol": "BTC-USD-PERP",
            "market_type": "perpetual",
            "venue_preference": None,
        },
        "activation": {
            "operator": "all",
            "conditions": [{"field": "close", "operator": "above", "value": 65000}],
        },
        "invalidation": {
            "operator": "any",
            "conditions": [{"field": "close", "operator": "below", "value": 64200}],
        },
        "lineage": {
            "signal_ids": ["sig_fixture_001"],
            "scenario_ids": ["scn_fixture_001"],
            "source_item_ids": ["src_fixture_001"],
        },
        "risk": {
            "risk_status": "not_evaluated",
            "requested_size": None,
            "requested_leverage": None,
            "approved_size": None,
            "approved_leverage": None,
            "risk_decision_id": None,
        },
        "execution": {
            "execution_gateway_status": "disabled",
            "live_execution_allowed": False,
            "order_creation_allowed": False,
            "paper_execution_allowed": False,
            "order_id": None,
        },
        "governance": {
            "authority_level": "level_0_observation_only",
            "operator_approval_status": "not_requested",
            "self_authority_change_allowed": False,
        },
    }


def candles() -> list[dict]:
    return [
        {"closed_at_utc": "2026-07-24T09:05:00Z", "open": 64800, "high": 65020, "low": 64750, "close": 64980},
        {"closed_at_utc": "2026-07-24T09:10:00Z", "open": 64980, "high": 65120, "low": 64940, "close": 65050},
        {"closed_at_utc": "2026-07-24T09:15:00Z", "open": 65050, "high": 65200, "low": 65010, "close": 65180},
    ]


def test_fixture_candidate_creates_deterministic_paper_fill_without_live_authority(tmp_path: Path) -> None:
    ledger = PaperLedger(tmp_path / "paper_ledger.jsonl")

    result = ledger.evaluate(candidate(), candles())

    assert result["status"] == "paper_filled"
    assert result["venue"] == "hyperliquid_simulation"
    assert result["execution_mode"] == "paper_only"
    assert result["paper_fill_price"] == 65050
    assert result["live_order_created"] is False
    assert result["private_venue_called"] is False
    assert result["human_approval_required_for_live_execution"] is True
    assert result["paper_order_id"].startswith("paper_")
    assert result["candidate_id"] == "cand_step9c_fixture_001"


def test_same_candidate_and_fixture_is_idempotent_and_append_only(tmp_path: Path) -> None:
    path = tmp_path / "paper_ledger.jsonl"
    ledger = PaperLedger(path)

    first = ledger.evaluate(candidate(), candles())
    second = ledger.evaluate(candidate(), candles())

    assert first == second
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["paper_order_id"] == first["paper_order_id"]


def test_expired_candidate_is_rejected_without_paper_fill(tmp_path: Path) -> None:
    ledger = PaperLedger(tmp_path / "paper_ledger.jsonl")
    late = candles()
    late[1]["closed_at_utc"] = "2026-07-24T10:05:00Z"
    late[2]["closed_at_utc"] = "2026-07-24T10:10:00Z"

    result = ledger.evaluate(candidate(), late)

    assert result["status"] == "rejected"
    assert result["reason_code"] == "candidate_expired_before_activation"
    assert result["live_order_created"] is False


def test_candidate_cannot_grant_itself_execution_or_approval_authority(tmp_path: Path) -> None:
    unsafe = deepcopy(candidate())
    unsafe["execution"]["live_execution_allowed"] = True
    unsafe["execution"]["order_creation_allowed"] = True
    unsafe["governance"]["operator_approval_status"] = "approved"
    unsafe["governance"]["self_authority_change_allowed"] = True

    ledger = PaperLedger(tmp_path / "paper_ledger.jsonl")

    try:
        ledger.evaluate(unsafe, candles())
    except PaperLedgerError as exc:
        assert exc.code == "authority_invariant_violation"
    else:
        raise AssertionError("unsafe candidate was accepted")

    assert not (tmp_path / "paper_ledger.jsonl").exists()


def test_fixture_runner_materializes_paper_result_ledger_and_closed_authority(tmp_path: Path) -> None:
    output = tmp_path / "step9c-run"

    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "run_step9c_paper_fixture.py"), "--output-dir", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads((output / "paper_result.json").read_text(encoding="utf-8"))
    blueprint = json.loads((output / "execution_blueprint.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (output / "paper_ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    assert result["status"] == "paper_filled"
    assert rows == [result]
    assert blueprint["execution_enabled"] is False
    assert blueprint["future_live_execution"]["human_approval_required"] is True
    assert "live_order" not in completed.stdout.lower()


def test_future_execution_blueprint_is_permanently_human_approval_gated() -> None:
    blueprint = execution_blueprint()

    assert blueprint["current_mode"] == "paper_only"
    assert blueprint["execution_enabled"] is False
    assert blueprint["wallet_enabled"] is False
    assert blueprint["private_api_enabled"] is False
    assert blueprint["future_live_execution"]["human_approval_required"] is True
    assert blueprint["future_live_execution"]["autonomous_approval_allowed"] is False
    assert blueprint["future_live_execution"]["approval_scope"] == "one_order_or_bounded_batch"
