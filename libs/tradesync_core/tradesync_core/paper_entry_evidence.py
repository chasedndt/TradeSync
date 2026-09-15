"""Entry evidence for a managed paper position: only facts observed and received before its entry.

Every item an entry considers is listed whether or not it arrived, so an absent
source is an explicit missing marker with its reason, never a silent gap. Each
record carries when the fact was observed and when TradeSync received it, and its
age at entry. A record observed or received after the entry time, or lacking either
time, is excluded and listed with the reason: nothing learned later can enter an
earlier decision.

The document carries a schema version. ``digest`` is the SHA-256 of its canonical
JSON, which is also the form it is stored in, so the stored copy can be checked
against the fingerprint kept beside it.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any, Mapping

SCHEMA_VERSION = "managed-paper-entry-evidence-v2"
CUTOFF_RULE = "observed_at <= entry_time and received_at <= entry_time"
MAX_EXCLUDED_LISTED = 50

ITEMS: tuple[tuple[str, str], ...] = (
    ("opportunity", "Opportunity"),
    ("scorer_verdict", "Scorer verdict"),
    ("features", "Feature observations"),
    ("horizon_measurement", "Timeframe measurement"),
    ("resting_liquidity", "Resting liquidity walls near price"),
    ("liquidations", "Liquidations received"),
    ("open_interest", "Open interest"),
    ("funding", "Funding rows"),
    ("thesis_edition", "Thesis edition"),
)
RESERVED = frozenset({"schema_version", "entry_time", "cutoff_rule", "items", "excluded_count", "authority", "scoring_influence"})


def _time(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def exclusion(record: Any, entry_time: float) -> str | None:
    """Why a record cannot be part of an entry at ``entry_time``, or None when it can."""
    if not isinstance(record, Mapping):
        return "not a record"
    observed, received = record.get("observed_at"), record.get("received_at")
    if not _time(observed):
        return "observed time unknown"
    if not _time(received):
        return "received time unknown"
    if observed > entry_time:
        return "observed after entry"
    if received > entry_time:
        return "received after entry"
    return None


def _item(label: str, raw: Mapping[str, Any] | None, entry_time: float) -> dict[str, Any]:
    raw = raw if isinstance(raw, Mapping) else None
    kept: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for record in (raw or {}).get("records") or []:
        reason = exclusion(record, entry_time)
        if reason:
            fields = record if isinstance(record, Mapping) else {}
            excluded.append({"reason": reason, "observed_at": fields.get("observed_at"),
                             "received_at": fields.get("received_at"), "id": fields.get("id")})
            continue
        kept.append({**copy.deepcopy(dict(record)), "age_s": entry_time - record["observed_at"]})
    if kept:
        reason = None
    elif excluded:
        reason = "every record was observed or received after entry"
    elif raw is None:
        reason = "not gathered"
    else:
        reason = raw.get("reason") or "source returned no records"
    return {"label": label, "source": (raw or {}).get("source"), "status": "present" if kept else "missing",
            "reason": reason, "coverage": (raw or {}).get("coverage"), "records": kept,
            "newest_age_s": min((record["age_s"] for record in kept), default=None),
            "excluded_count": len(excluded), "excluded": excluded[:MAX_EXCLUDED_LISTED]}


def document(gathered: Mapping[str, Mapping[str, Any]], entry_time: float, *, inputs: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The frozen entry record: each item after the cut-off, plus the inputs the plan was computed from."""
    if not _time(entry_time):
        raise ValueError("Finite positive entry time required")
    extra = dict(inputs or {})
    clash = RESERVED & extra.keys()
    if clash:
        raise ValueError(f"Entry inputs cannot replace evidence fields: {sorted(clash)}")
    items = {key: _item(label, gathered.get(key), entry_time) for key, label in ITEMS}
    return canonical({"schema_version": SCHEMA_VERSION, "entry_time": entry_time, "cutoff_rule": CUTOFF_RULE,
                      "items": items, "excluded_count": sum(item["excluded_count"] for item in items.values()),
                      "authority": "paper_only", "scoring_influence": False, **extra})


def canonical(value: Any) -> Any:
    """A JSON-native copy that reads back from PostgreSQL JSONB as the same canonical text."""
    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Evidence numbers must be finite")
        if value.is_integer() and abs(value) >= 1e15:
            return int(value)  # JSONB prints large whole numbers without an exponent
        return value + 0.0  # no negative zero: JSONB has none
    if isinstance(value, Mapping):
        return {str(key): canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical(item) for item in value]
    return str(value)


def canonical_json(value: Any) -> str:
    return json.dumps(canonical(value), sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
