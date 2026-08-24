"""Fail-closed bridge contract for ChaseOS, Strike Zone, and TradeSync.

The envelope is deliberately paper-only.  A ChaseOS approval represented here
authorizes one TradeSync paper evaluation; it is never an exchange-order,
wallet, credential, signing, or live-dispatch capability.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
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
    digest_value = str(approval["approval_digest"])
    if len(digest_value) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in digest_value):
        raise ControlEnvelopeError("invalid_approval", "approval_digest must be a SHA-256 hex digest")
    approved_at = _utc(approval["approved_at_utc"], "approved_at_utc")
    expires_at = _utc(candidate.get("expires_at_utc"), "candidate.expires_at_utc")
    if approved_at > expires_at:
        raise ControlEnvelopeError("approval_after_expiry", "approval occurred after candidate expiry")

    unsigned = {key: deepcopy(value) for key, value in envelope.items() if key != "envelope_id"}
    expected_id = "tce_" + canonical_hash(unsigned)[:32]
    if envelope.get("envelope_id") != expected_id:
        raise ControlEnvelopeError("envelope_integrity_failure", "envelope ID does not match its contents")
    return deepcopy(envelope)


class ApprovalConsumptionStore:
    """Durably consume each paper approval exactly once.

    SQLite provides one transactional authority record for the current
    local-first, single-host paper bridge. The record is committed before any
    evaluation begins: if the process fails afterward, a fresh approval is
    required instead of risking replay of an uncertain action.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS approval_consumptions (
                    approval_id TEXT PRIMARY KEY,
                    approval_decision_id TEXT NOT NULL UNIQUE,
                    envelope_id TEXT NOT NULL UNIQUE,
                    approval_digest TEXT NOT NULL,
                    candidate_hash TEXT NOT NULL,
                    consumed_at_utc TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def consume(
        self, envelope: dict[str, Any], *, consumed_at_utc: str
    ) -> dict[str, str]:
        validated = validate_paper_control_envelope(envelope)
        consumed_at = _utc(consumed_at_utc, "consumed_at_utc")
        valid_from = _utc(validated["candidate"]["valid_from_utc"], "candidate.valid_from_utc")
        expires_at = _utc(validated["candidate"]["expires_at_utc"], "candidate.expires_at_utc")
        if consumed_at < valid_from:
            raise ControlEnvelopeError("approval_not_yet_valid", "candidate validity window has not started")
        if consumed_at > expires_at:
            raise ControlEnvelopeError("approval_expired", "candidate expired before approval consumption")

        approval = validated["approval"]
        record = {
            "approval_id": str(approval["approval_id"]),
            "approval_decision_id": str(approval["approval_decision_id"]),
            "envelope_id": str(validated["envelope_id"]),
            "approval_digest": str(approval["approval_digest"]).lower(),
            "candidate_hash": str(validated["candidate_hash"]),
            "consumed_at_utc": consumed_at.isoformat().replace("+00:00", "Z"),
        }

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT * FROM approval_consumptions
                WHERE approval_id = ? OR approval_decision_id = ? OR envelope_id = ?
                """,
                (
                    record["approval_id"],
                    record["approval_decision_id"],
                    record["envelope_id"],
                ),
            ).fetchone()
            if existing is not None:
                connection.rollback()
                same_binding = all(
                    existing[key] == record[key]
                    for key in (
                        "approval_id",
                        "approval_decision_id",
                        "envelope_id",
                        "approval_digest",
                        "candidate_hash",
                    )
                )
                code = "approval_already_consumed" if same_binding else "approval_binding_conflict"
                raise ControlEnvelopeError(code, "paper approval has already been consumed")
            try:
                connection.execute(
                    """
                    INSERT INTO approval_consumptions (
                        approval_id, approval_decision_id, envelope_id,
                        approval_digest, candidate_hash, consumed_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    tuple(record.values()),
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise ControlEnvelopeError(
                    "approval_consumption_conflict",
                    "concurrent approval consumption was refused",
                ) from exc
        return record
