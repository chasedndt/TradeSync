"""Step 9C fixture-driven digital twin and append-only paper ledger.

This module never calls a venue, creates a live order, accesses credentials, or
changes execution authority. Future live execution is permanently represented as
human-approval gated; this paper evaluator cannot consume that approval.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from tradesync_core.control_envelope import (
    ApprovalConsumptionStore,
    validate_paper_control_envelope,
)


class PaperLedgerError(ValueError):
    """Fail-closed Step 9C contract error."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class _Window:
    valid_from: datetime
    evidence_cutoff: datetime
    expires_at: datetime


def _utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise PaperLedgerError("invalid_timestamp", f"invalid UTC timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise PaperLedgerError("invalid_timestamp", "timestamps must include UTC offset")
    return parsed.astimezone(timezone.utc)


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def execution_blueprint() -> dict[str, Any]:
    """Return the authority-closed future integration blueprint."""
    return {
        "schema_version": "tradesync_execution_blueprint_v1",
        "venue_vocabulary": "hyperliquid_only",
        "current_mode": "paper_only",
        "execution_enabled": False,
        "wallet_enabled": False,
        "private_api_enabled": False,
        "credential_access_enabled": False,
        "future_live_execution": {
            "human_approval_required": True,
            "autonomous_approval_allowed": False,
            "approval_scope": "one_order_or_bounded_batch",
            "approval_must_bind": [
                "candidate_id",
                "symbol",
                "side",
                "maximum_size",
                "maximum_leverage",
                "expiry",
            ],
            "required_pre_dispatch_gates": [
                "independent_risk_decision",
                "fresh_market_snapshot",
                "idempotency_key",
                "kill_switch_healthy",
                "operator_approval_unconsumed",
            ],
        },
    }


def _validate_candidate(candidate: dict[str, Any]) -> _Window:
    if candidate.get("schema_version") != "trade_candidate_v1":
        raise PaperLedgerError("unsupported_candidate_schema", "trade_candidate_v1 required")
    if not candidate.get("candidate_id"):
        raise PaperLedgerError("candidate_id_missing", "candidate_id required")
    if (candidate.get("candidate") or {}).get("status") != "review_only":
        raise PaperLedgerError("candidate_not_review_only", "only review_only candidates are admissible")

    execution = candidate.get("execution") or {}
    governance = candidate.get("governance") or {}
    risk = candidate.get("risk") or {}
    safe = (
        execution.get("execution_gateway_status") == "disabled"
        and execution.get("live_execution_allowed") is False
        and execution.get("order_creation_allowed") is False
        and execution.get("order_id") is None
        and governance.get("authority_level") == "level_0_observation_only"
        and governance.get("operator_approval_status") == "not_requested"
        and governance.get("self_authority_change_allowed") is False
        and risk.get("risk_status") == "not_evaluated"
        and risk.get("approved_size") is None
        and risk.get("approved_leverage") is None
    )
    if not safe:
        raise PaperLedgerError(
            "authority_invariant_violation",
            "candidate attempted to carry execution, approval, or evaluated-risk authority",
        )

    window = _Window(
        valid_from=_utc(candidate.get("valid_from_utc")),
        evidence_cutoff=_utc(candidate.get("evidence_cutoff_utc")),
        expires_at=_utc(candidate.get("expires_at_utc")),
    )
    if not (window.evidence_cutoff <= window.valid_from < window.expires_at):
        raise PaperLedgerError("invalid_candidate_window", "candidate time window is not ordered")
    return window


def _condition_matches(condition: dict[str, Any], candle: dict[str, Any]) -> bool:
    field = condition.get("field")
    if field not in candle:
        return False
    actual = float(candle[field])
    expected = float(condition["value"])
    operator = condition.get("operator")
    if operator == "above":
        return actual > expected
    if operator == "below":
        return actual < expected
    if operator == "at_or_above":
        return actual >= expected
    if operator == "at_or_below":
        return actual <= expected
    raise PaperLedgerError("unsupported_condition_operator", f"unsupported operator: {operator!r}")


def _condition_group_matches(group: dict[str, Any], candle: dict[str, Any]) -> bool:
    conditions = group.get("conditions") or []
    if not conditions:
        return False
    matches = [_condition_matches(condition, candle) for condition in conditions]
    operator = group.get("operator")
    if operator == "all":
        return all(matches)
    if operator == "any":
        return any(matches)
    raise PaperLedgerError("unsupported_condition_group", f"unsupported group operator: {operator!r}")


class PaperLedger:
    """Deterministic paper evaluator backed by an append-only JSONL ledger."""

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def _existing(self, simulation_id: str) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("simulation_id") == simulation_id:
                return row
        return None

    def _append(self, row: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())

    def evaluate(self, candidate: dict[str, Any], candles: Iterable[dict[str, Any]]) -> dict[str, Any]:
        window = _validate_candidate(candidate)
        fixture = sorted((dict(row) for row in candles), key=lambda row: row["closed_at_utc"])
        fixture_hash = _canonical_hash(fixture)
        simulation_id = "sim_" + _canonical_hash(
            {"candidate_id": candidate["candidate_id"], "fixture_hash": fixture_hash, "engine": "step9c_v1"}
        )[:32]
        existing = self._existing(simulation_id)
        if existing is not None:
            return existing

        base: dict[str, Any] = {
            "schema_version": "paper_ledger_entry_v1",
            "simulation_id": simulation_id,
            "candidate_id": candidate["candidate_id"],
            "fixture_hash": fixture_hash,
            "venue": "hyperliquid_simulation",
            "execution_mode": "paper_only",
            "live_order_created": False,
            "private_venue_called": False,
            "credential_accessed": False,
            "wallet_action_performed": False,
            "human_approval_required_for_live_execution": True,
            "autonomous_live_approval_allowed": False,
        }

        activation = candidate.get("activation") or {}
        invalidation = candidate.get("invalidation") or {}
        eligible_seen = False
        for candle in fixture:
            closed_at = _utc(candle["closed_at_utc"])
            if closed_at <= window.evidence_cutoff or closed_at < window.valid_from:
                continue
            eligible_seen = True
            if closed_at > window.expires_at:
                row = {**base, "status": "rejected", "reason_code": "candidate_expired_before_activation"}
                self._append(row)
                return row
            if _condition_group_matches(invalidation, candle):
                row = {**base, "status": "rejected", "reason_code": "candidate_invalidated_before_activation"}
                self._append(row)
                return row
            if _condition_group_matches(activation, candle):
                paper_order_id = "paper_" + _canonical_hash(
                    {"simulation_id": simulation_id, "closed_at_utc": candle["closed_at_utc"], "close": candle["close"]}
                )[:32]
                row = {
                    **base,
                    "status": "paper_filled",
                    "reason_code": "activation_observed_on_closed_fixture_candle",
                    "paper_order_id": paper_order_id,
                    "paper_fill_price": candle["close"],
                    "paper_filled_at_utc": candle["closed_at_utc"],
                    "side": candidate["candidate"]["direction"],
                    "symbol": candidate["instrument"]["canonical_symbol"],
                    "requested_size": None,
                    "requested_leverage": None,
                }
                self._append(row)
                return row

        reason = "activation_not_observed" if eligible_seen else "no_eligible_closed_candles"
        row = {**base, "status": "no_fill", "reason_code": reason}
        self._append(row)
        return row


def evaluate_approved_envelope(
    envelope: dict[str, Any],
    candles: Iterable[dict[str, Any]],
    *,
    paper_ledger: PaperLedger,
    consumption_store: ApprovalConsumptionStore,
    consumed_at_utc: str,
) -> dict[str, Any]:
    """Consume one paper approval before evaluating its immutable candidate.

    This bridge has no live-order, wallet, credential, signer or private API
    dependency. Consumption is intentionally not rolled back if later local
    evaluation fails, because replay after an uncertain outcome is less safe
    than requiring a new human decision.
    """
    validated = validate_paper_control_envelope(envelope)
    consumption = consumption_store.consume(
        validated, consumed_at_utc=consumed_at_utc
    )
    result = paper_ledger.evaluate(validated["candidate"], candles)
    return {
        "schema_version": "approved_paper_evaluation_v1",
        "envelope_id": validated["envelope_id"],
        "approval_consumption": consumption,
        "paper_result": result,
        "live_order_created": False,
        "wallet_action_performed": False,
        "credential_accessed": False,
    }
