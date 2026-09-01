"""Fail-closed bridge contract for ChaseOS, Strike Zone, and TradeSync.

The envelope is deliberately paper-only.  A ChaseOS approval represented here
authorizes one TradeSync paper evaluation; it is never an exchange-order,
wallet, credential, signing, or live-dispatch capability.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


class ControlEnvelopeError(ValueError):
    """A cross-system packet failed its authority or integrity contract."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


CLOSED_AUTHORITY = {
    "paper_evaluation_authorized": True,
    "live_execution_authorized": False,
    "wallet_authorized": False,
    "credential_access_authorized": False,
    "signing_authorized": False,
    "private_api_authorized": False,
    "authority_escalation_allowed": False,
}


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _utc(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ControlEnvelopeError("invalid_timestamp", f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ControlEnvelopeError("invalid_timestamp", f"{field} must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def build_paper_control_envelope(
    candidate: dict[str, Any],
    *,
    approval_id: str,
    approval_digest: str,
    approval_decision_id: str,
    approved_at_utc: str,
) -> dict[str, Any]:
    """Bind one authenticated ChaseOS decision to one immutable paper candidate."""
    candidate_copy = deepcopy(candidate)
    body = {
        "schema_version": "tradesync_control_envelope_v1",
        "source_system": "strikezone_crypto",
        "control_plane": "chaseos",
        "destination_system": "tradesync",
        "venue": "hyperliquid",
        "mode": "paper_only",
        "candidate": candidate_copy,
        "candidate_hash": canonical_hash(candidate_copy),
        "approval": {
            "approval_id": approval_id,
            "approval_digest": approval_digest,
            "approval_decision_id": approval_decision_id,
            "decision": "approved",
            "scope": "once",
            "approved_at_utc": approved_at_utc,
            "authorizes": "paper_evaluation_only",
        },
        "authority": deepcopy(CLOSED_AUTHORITY),
    }
    body["envelope_id"] = "tce_" + canonical_hash(body)[:32]
    return validate_paper_control_envelope(body)


def validate_paper_control_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    """Validate integrity, expiry, identity, and the closed authority ceiling."""
    required = {
        "schema_version", "source_system", "control_plane", "destination_system",
        "venue", "mode", "candidate", "candidate_hash", "approval", "authority", "envelope_id",
    }
    if set(envelope) != required or envelope.get("schema_version") != "tradesync_control_envelope_v1":
        raise ControlEnvelopeError("invalid_envelope_schema", "tradesync_control_envelope_v1 required")
    identity = (
        envelope.get("source_system") == "strikezone_crypto"
        and envelope.get("control_plane") == "chaseos"
        and envelope.get("destination_system") == "tradesync"
        and envelope.get("venue") == "hyperliquid"
        and envelope.get("mode") == "paper_only"
    )
    if not identity:
        raise ControlEnvelopeError("invalid_system_boundary", "envelope system or venue boundary is invalid")
    if envelope.get("authority") != CLOSED_AUTHORITY:
        raise ControlEnvelopeError("authority_invariant_violation", "paper-only closed authority is required")

    candidate = envelope.get("candidate")
    if not isinstance(candidate, dict) or candidate.get("schema_version") != "trade_candidate_v1":
        raise ControlEnvelopeError("invalid_candidate", "embedded trade_candidate_v1 required")
    if envelope.get("candidate_hash") != canonical_hash(candidate):
        raise ControlEnvelopeError("candidate_integrity_failure", "candidate hash does not match payload")
    if (candidate.get("candidate") or {}).get("status") != "review_only":
        raise ControlEnvelopeError("candidate_not_review_only", "candidate must remain review_only")
    execution = candidate.get("execution") or {}
    governance = candidate.get("governance") or {}
    if not (
        execution.get("execution_gateway_status") == "disabled"
        and execution.get("live_execution_allowed") is False
        and execution.get("order_creation_allowed") is False
        and governance.get("self_authority_change_allowed") is False
    ):
        raise ControlEnvelopeError("authority_invariant_violation", "candidate carries prohibited authority")

    approval = envelope.get("approval")
    approval_fields = {
        "approval_id", "approval_digest", "approval_decision_id", "decision",
        "scope", "approved_at_utc", "authorizes",
    }
    if not isinstance(approval, dict) or set(approval) != approval_fields:
        raise ControlEnvelopeError("invalid_approval", "approval binding schema is invalid")
    if (
        approval.get("decision") != "approved"
        or approval.get("scope") != "once"
        or approval.get("authorizes") != "paper_evaluation_only"
        or not all(str(approval.get(key) or "").strip() for key in ("approval_id", "approval_digest", "approval_decision_id"))
    ):
        raise ControlEnvelopeError("invalid_approval", "single-use paper approval is required")
    approved_at = _utc(approval["approved_at_utc"], "approved_at_utc")
    expires_at = _utc(candidate.get("expires_at_utc"), "candidate.expires_at_utc")
    if approved_at > expires_at:
        raise ControlEnvelopeError("approval_after_expiry", "approval occurred after candidate expiry")

    unsigned = {key: deepcopy(value) for key, value in envelope.items() if key != "envelope_id"}
    expected_id = "tce_" + canonical_hash(unsigned)[:32]
    if envelope.get("envelope_id") != expected_id:
        raise ControlEnvelopeError("envelope_integrity_failure", "envelope ID does not match its contents")
    return deepcopy(envelope)
