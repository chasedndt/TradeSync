"""Turn an authenticated Strike Zone Pine receipt into a `trade_candidate_v1`.

Strike Zone Crypto is a Pine Script repository, not a service — corrected
2026-09-08. Its output reaches TradeSync as a TradingView alert, so the receipt
is an alert body that has already been authenticated by
``tradingview_webhook.parse_alert``. What is missing until now is the step after
that: turning a receipt into the candidate structure the paper ledger consumes.

**A candidate is paper research.** The roadmap says so in as many words:
"candidates remain paper research." That is enforced here rather than trusted.

The single design rule, and the reason this module exists at all:

    Authority fields are *written* by this adapter, never *copied* from the
    receipt.

`status`, `authority_level`, `operator_approval_status`,
`execution_gateway_status`, `live_execution_allowed`, `order_creation_allowed`,
`risk_status` — every one is a constant here. A Pine script is a text file on a
third party's server that anybody with the alert URL can aim at this endpoint.
If it could set `live_execution_allowed`, it would be a remote execution
primitive with a webhook for an interface.

A receipt that *tries* to set one is refused rather than silently overwritten,
for the same reason quarantine refuses privilege escalation by name: the attempt
is the finding.

Everything produced here satisfies ``paper_ledger._validate_candidate``, which
independently re-checks the same invariants. Two locks, one key, on purpose.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

SCHEMA_VERSION = "trade_candidate_v1"
RECEIPT_SCHEMA = "strike_zone_receipt_v1"

# The candidate's whole authority posture, fixed. Written, never read from a
# receipt. These exact values are what paper_ledger requires.
FIXED_CANDIDATE_STATUS = "review_only"
FIXED_AUTHORITY = {
    "authority_level": "level_0_observation_only",
    "operator_approval_status": "not_requested",
    "self_authority_change_allowed": False,
}
FIXED_EXECUTION = {
    "execution_gateway_status": "disabled",
    "live_execution_allowed": False,
    "order_creation_allowed": False,
    "paper_execution_allowed": False,
    "order_id": None,
}
FIXED_RISK = {
    "risk_status": "not_evaluated",
    "requested_size": None,
    "requested_leverage": None,
    "approved_size": None,
    "approved_leverage": None,
    "risk_decision_id": None,
}

# Any of these in a receipt is an attempt to set its own authority.
FORBIDDEN_RECEIPT_FIELDS = frozenset(
    {
        "approved",
        "authority",
        "authority_level",
        "execution",
        "execution_gateway_status",
        "governance",
        "live_execution_allowed",
        "operator_approval_status",
        "order_creation_allowed",
        "order_id",
        "risk",
        "risk_status",
        "approved_size",
        "approved_leverage",
        "status",
        "self_authority_change_allowed",
    }
)

DIRECTIONS = {"long", "short"}
# Conditions the ledger's evaluator understands. A receipt naming anything else
# would produce a candidate that silently never activates.
CONDITION_FIELDS = {"close", "high", "low", "open"}
CONDITION_OPERATORS = {"above", "below", "at_or_above", "at_or_below"}

DEFAULT_VALIDITY = timedelta(hours=4)


class ReceiptError(ValueError):
    """A Strike Zone receipt cannot become a candidate, with the reason."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def validate_receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Check a Pine receipt before anything is built from it."""
    if not isinstance(payload, Mapping):
        raise ReceiptError("malformed_receipt", "receipt must be a JSON object")

    reached_for = sorted(FORBIDDEN_RECEIPT_FIELDS.intersection(payload))
    if reached_for:
        raise ReceiptError(
            "authority_claimed",
            "receipt tries to set its own authority: "
            + ", ".join(reached_for)
            + ". A Pine script is a text file on a third party's server; if it "
            "could set these, this endpoint would be a remote execution "
            "primitive.",
        )

    for field in ("indicator", "ticker", "direction"):
        if not payload.get(field):
            raise ReceiptError("missing_field", f"receipt must carry {field!r}")

    direction = str(payload["direction"]).strip().lower()
    if direction not in DIRECTIONS:
        raise ReceiptError(
            "unknown_direction",
            f"direction {payload['direction']!r} is not one of: "
            + ", ".join(sorted(DIRECTIONS)),
        )

    activation = _conditions(payload.get("activation"), "activation")
    invalidation = _conditions(payload.get("invalidation"), "invalidation")
    if not activation["conditions"]:
        raise ReceiptError(
            "no_activation",
            "a candidate with no activation condition can never activate, so it "
            "is a record of nothing",
        )

    return {
        "schema_version": RECEIPT_SCHEMA,
        "indicator": str(payload["indicator"]),
        "ticker": str(payload["ticker"]),
        "direction": direction,
        "interval": str(payload.get("interval") or ""),
        "activation": activation,
        "invalidation": invalidation,
        "note": str(payload.get("note") or ""),
    }


def _conditions(raw: Any, label: str) -> dict[str, Any]:
    """Normalise one condition group, refusing anything unevaluable."""
    if raw is None:
        return {"operator": "all", "conditions": []}
    if not isinstance(raw, Mapping):
        raise ReceiptError("malformed_conditions", f"{label} must be an object")

    operator = str(raw.get("operator") or "all").lower()
    if operator not in {"all", "any"}:
        raise ReceiptError(
            "unknown_group_operator",
            f"{label} operator {operator!r} must be 'all' or 'any'",
        )

    out = []
    for index, condition in enumerate(raw.get("conditions") or []):
        if not isinstance(condition, Mapping):
            raise ReceiptError("malformed_conditions", f"{label}[{index}] is not an object")
        field = str(condition.get("field") or "").lower()
        comparator = str(condition.get("operator") or "").lower()
        if field not in CONDITION_FIELDS:
            raise ReceiptError(
                "unknown_condition_field",
                f"{label}[{index}] field {field!r} is not one of: "
                + ", ".join(sorted(CONDITION_FIELDS)),
            )
        if comparator not in CONDITION_OPERATORS:
            raise ReceiptError(
                "unknown_condition_operator",
                f"{label}[{index}] operator {comparator!r} is not one of: "
                + ", ".join(sorted(CONDITION_OPERATORS)),
            )
        value = condition.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ReceiptError(
                "non_numeric_condition",
                f"{label}[{index}] value must be a number, got {value!r}",
            )
        out.append({"field": field, "operator": comparator, "value": float(value)})

    return {"operator": operator, "conditions": out}


def to_trade_candidate(
    receipt: Mapping[str, Any],
    *,
    canonical_symbol: str,
    asset: str,
    observed_at: datetime,
    validity: timedelta = DEFAULT_VALIDITY,
    source_item_id: str = "",
) -> dict[str, Any]:
    """Build a `trade_candidate_v1` from a validated receipt.

    ``observed_at`` is the evidence cutoff: the candidate may not be evaluated
    against any candle that closed before the alert existed, or it would be
    scored on data the Pine script could not have seen. The paper ledger
    re-checks the ordering independently.
    """
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise ReceiptError(
            "unvalidated_receipt",
            "pass the output of validate_receipt, not a raw alert body",
        )
    if observed_at.tzinfo is None:
        raise ReceiptError("naive_timestamp", "observed_at must carry a UTC offset")
    if validity <= timedelta(0):
        raise ReceiptError("invalid_validity", "validity must be positive")

    cutoff = observed_at.astimezone(timezone.utc)
    candidate_id = "sz_" + _digest(
        {
            "indicator": receipt["indicator"],
            "ticker": receipt["ticker"],
            "direction": receipt["direction"],
            "activation": receipt["activation"],
            "cutoff": cutoff.isoformat(),
        }
    )[:24]

    return {
        "schema_version": SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "created_at_utc": _iso(cutoff),
        "valid_from_utc": _iso(cutoff),
        "evidence_cutoff_utc": _iso(cutoff),
        "expires_at_utc": _iso(cutoff + validity),
        "candidate": {
            # Constant. Not read from the receipt, at any depth.
            "status": FIXED_CANDIDATE_STATUS,
            "direction": receipt["direction"],
            "candidate_type": "directional",
        },
        "instrument": {
            "asset": asset,
            "canonical_symbol": canonical_symbol,
            "market_type": "perpetual",
            "venue_preference": None,
        },
        "activation": receipt["activation"],
        "invalidation": receipt["invalidation"],
        "lineage": {
            "signal_ids": [],
            "scenario_ids": [],
            # What produced it, so a candidate is traceable to the alert and the
            # Pine indicator that raised it.
            "source_item_ids": [source_item_id] if source_item_id else [],
            "indicator": receipt["indicator"],
            "interval": receipt["interval"],
        },
        "risk": dict(FIXED_RISK),
        "execution": dict(FIXED_EXECUTION),
        "governance": dict(FIXED_AUTHORITY),
    }


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
