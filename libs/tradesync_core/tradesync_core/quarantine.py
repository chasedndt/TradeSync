"""Admission control for anything TradeSync did not observe itself.

Every Tier B connector — Strike Zone, agent harnesses, ChaseOS snapshots,
TradingView alerts — sends material that TradeSync did not measure. That
material must never land directly in the evidence the system later uses to
judge itself. It lands here first.

The path is: **quarantine -> extraction -> proposed delta -> approved
promotion.** Nothing skips a step, and promotion is an operator act.

Why this is not paranoia. The system already learned the lesson twice in one
day: a healthcheck that only proved the port was open reported an hour-long
outage as healthy, and a hit rate without a base rate reported a falling market
as skill. Both were cases of accepting a signal without checking what it
actually asserted. An unauthenticated external writer is the same failure with
a motivated adversary attached.

Rules enforced here:

- **Untrusted by default.** Admission is a decision with recorded reasons, never
  an absence of objection.
- **A payload is data, never instruction.** Nothing in a submission can raise
  its own trust level, and any field claiming to do so is a rejection reason.
- **Tier B never gates Tier A.** Admitted external evidence is enrichment. It
  cannot approve, execute, or become a directional signal on its own.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "quarantine_v1"

# Sources permitted to submit at all. An unknown source is rejected rather than
# accepted with a warning, so adding a connector is a deliberate act.
KNOWN_SOURCES = frozenset(
    {"tradingview", "strike_zone", "agent_harness", "chaseos", "operator", "discord"}
)

# Fields a submission must never set. These name trust, authority or identity,
# and a payload that tries to set its own is attempting privilege escalation.
FORBIDDEN_FIELDS = frozenset(
    {
        "admitted",
        "approved",
        "authority",
        "execution_authority",
        "scoring_allowed",
        "signal_kind",
        "provenance",
        "trust",
        "tier",
    }
)

MAX_PAYLOAD_BYTES = 64 * 1024
MAX_CLOCK_SKEW_MS = 120_000
DEFAULT_MAX_AGE_MS = 15 * 60_000


class QuarantineError(ValueError):
    """Raised for malformed calls, never for an ordinary rejection."""


@dataclass(frozen=True)
class IntakeVerdict:
    """Whether a submission may enter quarantine, and why."""

    accepted: bool
    source: str
    content_digest: str
    reasons: list[dict[str, str]] = field(default_factory=list)
    normalized: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "accepted": self.accepted,
            "source": self.source,
            "content_digest": self.content_digest,
            "reasons": self.reasons,
            # Stated on every verdict so no consumer can mistake quarantined
            # material for admitted evidence.
            "authority": "none",
            "tier": "B",
        }


def content_digest(payload: Mapping[str, Any]) -> str:
    """Stable digest of the submission, for replay and duplicate detection."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()


def _reason(code: str, detail: str) -> dict[str, str]:
    return {"code": code, "detail": detail}


def evaluate_submission(
    source: str,
    payload: Mapping[str, Any],
    received_at_ms: int,
    observed_at_ms: int | None = None,
    max_age_ms: int = DEFAULT_MAX_AGE_MS,
    seen_digests: Sequence[str] = (),
) -> IntakeVerdict:
    """Decide whether one external submission may enter quarantine.

    Acceptance here means only "worth storing for review". It is not admission
    to the feature catalog and confers no authority whatsoever.
    """

    if not isinstance(payload, Mapping):
        raise QuarantineError("payload must be a mapping")
    if not isinstance(received_at_ms, int) or isinstance(received_at_ms, bool):
        raise QuarantineError("received_at_ms must be an integer")

    reasons: list[dict[str, str]] = []
    digest = content_digest(payload)

    if source not in KNOWN_SOURCES:
        reasons.append(
            _reason(
                "unknown_source",
                f"'{source}' is not a registered connector; adding one is a "
                "deliberate act, not an automatic consequence of submitting",
            )
        )

    encoded = json.dumps(payload, default=str).encode("utf-8")
    if len(encoded) > MAX_PAYLOAD_BYTES:
        reasons.append(
            _reason(
                "payload_too_large",
                f"{len(encoded)} bytes exceeds the {MAX_PAYLOAD_BYTES} byte bound",
            )
        )

    claimed = sorted(FORBIDDEN_FIELDS.intersection(payload.keys()))
    if claimed:
        reasons.append(
            _reason(
                "payload_claims_authority",
                "a submission may not set its own trust or authority: "
                + ", ".join(claimed),
            )
        )

    if digest in set(seen_digests):
        reasons.append(
            _reason(
                "duplicate_submission",
                "identical content already quarantined; re-sending does not "
                "make it more credible",
            )
        )

    if observed_at_ms is not None:
        if not isinstance(observed_at_ms, int) or isinstance(observed_at_ms, bool):
            raise QuarantineError("observed_at_ms must be an integer or None")
        age = received_at_ms - observed_at_ms
        if age < -MAX_CLOCK_SKEW_MS:
            reasons.append(
                _reason(
                    "timestamped_in_future",
                    f"observed {abs(age)} ms ahead of receipt, beyond tolerated skew",
                )
            )
        elif age > max_age_ms:
            reasons.append(
                _reason(
                    "submission_stale",
                    f"observed {age} ms before receipt, beyond the {max_age_ms} ms bound",
                )
            )

    return IntakeVerdict(
        accepted=not reasons,
        source=source,
        content_digest=digest,
        reasons=reasons,
        normalized=dict(payload) if not reasons else {},
    )


def promotion_blockers(
    verdict_accepted: bool,
    reviewed_by: str | None,
    target_provenance: str,
) -> list[dict[str, str]]:
    """Why this quarantined item may not yet become admitted evidence.

    An empty list means the operator has reviewed it and the target provenance
    is one the catalog can score. Promotion remains an operator act: this
    function reports readiness, it does not grant it.
    """

    blockers: list[dict[str, str]] = []
    if not verdict_accepted:
        blockers.append(
            _reason("never_accepted", "the submission did not pass intake")
        )
    if not reviewed_by:
        blockers.append(
            _reason(
                "operator_review_required",
                "promotion is an operator act; nothing self-promotes",
            )
        )
    if target_provenance not in {"observed", "derived"}:
        blockers.append(
            _reason(
                "provenance_not_scoreable",
                f"'{target_provenance}' may inform a human but can never reach "
                "a generic directional score",
            )
        )
    return blockers
