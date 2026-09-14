"""Which rulebook the paper scorer uses, and the operator actions that change it.

The rulebook file is the baseline. An adopted learning proposal is written to
``regime_rulebooks`` and activated in ``regime_weight_activations`` (migration
002, which already allows one active row per horizon). The core scorer reads
the active row every cycle and falls back to the file when there is none, so:

- **adopt** writes the proposal's rulebook, closes the current activation and
  opens a new one, and marks the proposal adopted, in one transaction. A
  proposal built on a rulebook that is no longer active is refused: its replay
  compared against the wrong baseline.
- **revert** goes back to the rulebook that was active before the current one
  was adopted (the adopting proposal's parent). When that parent is the file,
  the activation is simply closed and the scorer falls back to the file.

Nothing here runs automatically; every change names who made it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from tradesync_core.active_rulebook import ACTIVE_RULEBOOK_SQL as ACTIVE_SQL
from tradesync_core.active_rulebook import config_of as _config
from tradesync_core.active_rulebook import rulebook_from_config
from tradesync_core.regime_weights import RegimeRulebook, RulebookValidationError


class ActivationConflict(RuntimeError):
    """The requested change no longer matches what is active."""


@dataclass(frozen=True)
class ActiveRulebook:
    rulebook: RegimeRulebook
    source: str  # "database" | "file"
    activation_id: str | None = None
    activated_at: Any = None
    activated_by: str | None = None
    reason: str = ""

    def summary(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "rulebook_id": self.rulebook.rulebook_id,
            "version": self.rulebook.version,
            "digest": self.rulebook.digest,
            "weights": self.rulebook.weights,
            "feature_weights": self.rulebook.feature_weights,
            "activation_id": self.activation_id,
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "activated_by": self.activated_by,
            "reason": self.reason,
        }


async def read_active(conn, baseline: RegimeRulebook) -> ActiveRulebook:
    """The active rulebook for ``baseline``'s id, or the file when none is active or valid."""

    row = await conn.fetchrow(ACTIVE_SQL, baseline.rulebook_id)
    if not row:
        return ActiveRulebook(baseline, "file", reason="no adopted rulebook is active")
    try:
        rulebook = rulebook_from_config(row["config"])
    except (RulebookValidationError, ValueError, TypeError) as exc:
        return ActiveRulebook(baseline, "file", reason=f"active rulebook is invalid ({exc}); the file is used")
    return ActiveRulebook(
        rulebook, "database", str(row["activation_id"]), row["activated_at"], row["activated_by"],
        reason=f"adopted: {row['approval_reference'] or 'no reference'}",
    )


async def _ensure_rulebook_row(conn, rulebook: RegimeRulebook, created_by: str) -> str:
    row = await conn.fetchrow(
        """
        INSERT INTO regime_rulebooks (rulebook_id, version, schema_version, status, environment,
                                      horizon, config_digest, config, created_by)
        VALUES ($1, $2, $3, 'paper_active', 'paper', $4, $5, $6::jsonb, $7)
        ON CONFLICT (config_digest) DO UPDATE SET status = 'paper_active'
        RETURNING id
        """,
        rulebook.rulebook_id, rulebook.version, rulebook.data["schema_version"],
        rulebook.data["horizon"], rulebook.digest, json.dumps(rulebook.data), created_by,
    )
    return str(row["id"])


async def _close_current(conn, baseline: RegimeRulebook) -> Any:
    current = await conn.fetchrow(ACTIVE_SQL + " FOR UPDATE OF a", baseline.rulebook_id)
    if current:
        await conn.execute("UPDATE regime_weight_activations SET deactivated_at = now() WHERE id = $1",
                           current["activation_id"])
        await conn.execute("UPDATE regime_rulebooks SET status = 'retired' WHERE id = $1",
                           current["rulebook_row_id"])
    return current


async def _open(conn, rulebook_row_id: str, horizon: str, decided_by: str, reference: str) -> str:
    return str(await conn.fetchval(
        """
        INSERT INTO regime_weight_activations (regime_rulebook_id, horizon, environment, activated_by, approval_reference)
        VALUES ($1::uuid, $2, 'paper', $3, $4) RETURNING id
        """,
        rulebook_row_id, horizon, decided_by, reference,
    ))


async def adopt(conn, proposal: dict[str, Any], baseline: RegimeRulebook, decided_by: str, note: str) -> dict[str, Any]:
    """Activate a proposed rulebook. Call inside a transaction."""

    active = await read_active(conn, baseline)
    if proposal["parent_digest"] != active.rulebook.digest:
        raise ActivationConflict(
            f"proposal was built on {proposal['parent_version']} but {active.rulebook.version} is active; "
            "generate a new proposal"
        )
    rulebook = rulebook_from_config(proposal["config"])
    row_id = await _ensure_rulebook_row(conn, rulebook, decided_by)
    await _close_current(conn, baseline)
    activation_id = await _open(conn, row_id, rulebook.data["horizon"], decided_by, f"learning_proposal:{proposal['id']}")
    await conn.execute(
        """
        UPDATE learning_proposals
        SET status = 'adopted', decided_at = now(), decided_by = $2, decision_note = $3, activation_id = $4::uuid
        WHERE id = $1::uuid
        """,
        str(proposal["id"]), decided_by, note, activation_id,
    )
    return {"activation_id": activation_id, "version": rulebook.version, "digest": rulebook.digest}


async def revert(conn, baseline: RegimeRulebook, decided_by: str, note: str) -> dict[str, Any]:
    """Re-activate the rulebook active before the current one was adopted. Call inside a transaction."""

    current = await _close_current(conn, baseline)
    if not current:
        raise ActivationConflict("the rulebook file is already in use; there is nothing to revert")
    adopting = await conn.fetchrow(
        "SELECT id, parent_digest FROM learning_proposals WHERE config_digest = $1 AND status = 'adopted' "
        "ORDER BY decided_at DESC LIMIT 1",
        current["config_digest"],
    )
    if adopting:
        await conn.execute(
            "UPDATE learning_proposals SET reverted_at = now(), reverted_by = $2 WHERE id = $1",
            adopting["id"], decided_by,
        )
    parent_digest = adopting["parent_digest"] if adopting else None
    parent = None
    if parent_digest and parent_digest != baseline.digest:
        parent = await conn.fetchrow("SELECT id, config, version FROM regime_rulebooks WHERE config_digest = $1",
                                     parent_digest)
    if not parent:
        return {"source": "file", "version": baseline.version, "digest": baseline.digest, "note": note}
    await conn.execute("UPDATE regime_rulebooks SET status = 'paper_active' WHERE id = $1", parent["id"])
    horizon = _config(parent["config"])["horizon"]
    activation_id = await _open(conn, str(parent["id"]), horizon, decided_by, f"revert:{current['activation_id']}")
    return {"source": "database", "version": parent["version"], "digest": parent_digest, "activation_id": activation_id}


async def history(conn, baseline: RegimeRulebook, limit: int = 20) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT a.id, r.version, r.config_digest, a.activated_at, a.deactivated_at, a.activated_by, a.approval_reference
        FROM regime_weight_activations a JOIN regime_rulebooks r ON r.id = a.regime_rulebook_id
        WHERE a.environment = 'paper' AND r.rulebook_id = $1
        ORDER BY a.activated_at DESC LIMIT $2
        """,
        baseline.rulebook_id, limit,
    )
    return [
        {
            "activation_id": str(r["id"]), "version": r["version"], "digest": r["config_digest"],
            "activated_at": r["activated_at"].isoformat(), "activated_by": r["activated_by"],
            "deactivated_at": r["deactivated_at"].isoformat() if r["deactivated_at"] else None,
            "reference": r["approval_reference"],
        }
        for r in rows
    ]


async def scorer_last_used(conn) -> dict[str, Any] | None:
    """The rulebook recorded on the scorer's newest verdict: proof of what it is using."""

    row = await conn.fetchrow(
        """
        SELECT created_at, features->'evidence'->>'rulebook_version' AS version,
               features->'evidence'->>'rulebook_digest' AS digest
        FROM signals WHERE agent = 'regime_paper_scorer' ORDER BY created_at DESC LIMIT 1
        """
    )
    if not row:
        return None
    return {"at": row["created_at"].isoformat(), "version": row["version"], "digest": row["digest"]}
