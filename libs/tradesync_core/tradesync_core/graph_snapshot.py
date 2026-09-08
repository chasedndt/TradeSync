"""Validate a ChaseOS ``GraphSnapshot`` before it is projected locally.

ChaseOS is the canonical knowledge instance. TradeSync reads its snapshots and
keeps a local adjacency projection so that "why does this rule exist" can be
answered without a network call — and so that TradeSync keeps working when the
connector is offline, which the roadmap requires.

Three boundaries are enforced here rather than documented and hoped for:

**Read-only.** Nothing in this module writes anything. The snapshot is an input.
TradeSync never produces canonical knowledge, and the projection is derived
data that can be dropped and rebuilt from the artifact at any time.

**No authority.** A snapshot is evidence, never permission. A node or edge that
carries a field claiming scoring, approval or execution authority is refused
outright rather than stripped and accepted — a connector that tries to grant
itself authority is not a formatting problem, and quietly cleaning it up would
hide the attempt. This mirrors ``quarantine.FORBIDDEN_FIELDS``, for the same
reason and against the same threat.

**Referential integrity.** An edge whose endpoints are not both present is
refused. Projecting it would create a dangling adjacency row that later
recursive queries would silently walk off.

The artifact contract is ChaseOS's, at
``chaseos-core/runtime/graph/artifact.py``. This module does not redefine it; it
checks a document against it and normalises what the projection needs.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Iterable, Mapping

from .timeparse import TimestampError, parse_utc_allow_naive

# ChaseOS's own vocabularies. Kept as data rather than imported, because
# TradeSync must not take a code dependency on the ChaseOS runtime — the
# connector has to be optional.
CONFIDENCE_VALUES = frozenset({"EXTRACTED", "INFERRED", "AMBIGUOUS"})

# Fields a knowledge node may never carry. A snapshot describes what is known;
# it does not decide what may be traded, approved or executed. Same list and
# same rationale as the quarantine intake path.
FORBIDDEN_FIELDS = frozenset(
    {
        "admitted",
        "approved",
        "authority",
        "execution_authority",
        "scoring_allowed",
        "signal_kind",
        "provenance_authority",
        "trust",
        "tier",
    }
)

REQUIRED_NODE_FIELDS = ("node_id", "label", "node_type", "source_file")
REQUIRED_EDGE_FIELDS = ("edge_id", "source_id", "target_id", "relation")
REQUIRED_SNAPSHOT_FIELDS = ("snapshot_id", "created_at", "vault_root")


class SnapshotRejected(ValueError):
    """The snapshot cannot be projected, with the reason stated."""


def _reject(reason: str) -> None:
    raise SnapshotRejected(reason)


def _forbidden_in(properties: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(properties, Mapping):
        return []
    return sorted(FORBIDDEN_FIELDS.intersection(properties))


def parse_created_at(value: str) -> datetime:
    """ChaseOS writes ISO 8601 UTC; accept that, and refuse anything else.

    Substituting ``now()`` for an unparseable timestamp would date the snapshot
    to when TradeSync happened to read it, not when the knowledge was extracted.
    A snapshot with no honest creation time is not projected.

    Checked here rather than at projection time so that a malformed timestamp is
    the same kind of answer as every other contract violation — a stated refusal
    the operator can take back to ChaseOS, not a server error.
    """
    try:
        # Shared parser: one set of rules for the whole system. A naive
        # timestamp is refused rather than assumed to be UTC.
        return parse_utc_allow_naive(value, "created_at")
    except TimestampError as exc:
        raise SnapshotRejected(f"created_at {value!r} is not ISO 8601: {exc}") from exc


def validate_snapshot(document: Mapping[str, Any]) -> dict[str, Any]:
    """Check a snapshot document and return it normalised for projection.

    Raises ``SnapshotRejected`` with a stated reason. There is no partial
    acceptance: a snapshot is projected whole or not at all, because a
    half-projected graph answers adjacency questions wrongly rather than
    refusing to answer them.
    """
    if not isinstance(document, Mapping):
        _reject("snapshot must be a JSON object")

    missing = [f for f in REQUIRED_SNAPSHOT_FIELDS if not document.get(f)]
    if missing:
        _reject(f"snapshot is missing required fields: {', '.join(missing)}")

    # Raises SnapshotRejected on anything unparseable.
    parse_created_at(document["created_at"])

    raw_nodes = document.get("nodes")
    raw_edges = document.get("edges")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        _reject("snapshot must carry 'nodes' and 'edges' arrays")

    nodes = _validate_nodes(raw_nodes)
    edges = _validate_edges(raw_edges, {node["node_id"] for node in nodes})

    communities = document.get("community_assignments") or {}
    if not isinstance(communities, Mapping):
        _reject("community_assignments must be an object of node_id -> community_id")
    unknown = sorted(set(communities) - {node["node_id"] for node in nodes})
    if unknown:
        _reject(
            "community_assignments name nodes not in this snapshot: "
            + ", ".join(unknown[:5])
        )

    return {
        "snapshot_id": str(document["snapshot_id"]),
        "created_at": str(document["created_at"]),
        "vault_root": str(document["vault_root"]),
        "extraction_scope": list(document.get("extraction_scope") or []),
        "nodes": nodes,
        "edges": edges,
        "community_assignments": {str(k): int(v) for k, v in communities.items()},
        "build_info": dict(document.get("build_info") or {}),
        "metadata": dict(document.get("metadata") or {}),
        "content_digest": snapshot_digest(document),
    }


def _validate_nodes(raw_nodes: Iterable[Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()

    for index, raw in enumerate(raw_nodes):
        if not isinstance(raw, Mapping):
            _reject(f"node {index} is not an object")

        missing = [f for f in REQUIRED_NODE_FIELDS if not raw.get(f)]
        if missing:
            _reject(f"node {index} is missing: {', '.join(missing)}")

        node_id = str(raw["node_id"])
        if node_id in seen:
            # Node ids are content-derived and stable by contract. A duplicate
            # means the extraction is not deterministic, and projecting it would
            # pick an arbitrary winner.
            _reject(f"duplicate node_id {node_id!r}; snapshot ids must be unique")
        seen.add(node_id)

        confidence = str(raw.get("confidence") or "")
        if confidence not in CONFIDENCE_VALUES:
            _reject(
                f"node {node_id!r} has confidence {confidence!r}; expected one of "
                + ", ".join(sorted(CONFIDENCE_VALUES))
            )

        forbidden = _forbidden_in(raw.get("properties"))
        if forbidden:
            _reject(
                f"node {node_id!r} claims authority it cannot hold: "
                + ", ".join(forbidden)
                + ". Knowledge is evidence, never permission."
            )

        nodes.append(
            {
                "node_id": node_id,
                "label": str(raw["label"]),
                "node_type": str(raw["node_type"]),
                "source_file": str(raw["source_file"]),
                "source_line": _optional_int(raw.get("source_line")),
                "domain": _optional_str(raw.get("domain")),
                "project": _optional_str(raw.get("project")),
                "properties": dict(raw.get("properties") or {}),
                "confidence": confidence,
                "provenance": str(raw.get("provenance") or ""),
            }
        )
    return nodes


def _validate_edges(
    raw_edges: Iterable[Any], node_ids: set[str]
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    seen: set[str] = set()

    for index, raw in enumerate(raw_edges):
        if not isinstance(raw, Mapping):
            _reject(f"edge {index} is not an object")

        missing = [f for f in REQUIRED_EDGE_FIELDS if not raw.get(f)]
        if missing:
            _reject(f"edge {index} is missing: {', '.join(missing)}")

        edge_id = str(raw["edge_id"])
        if edge_id in seen:
            _reject(f"duplicate edge_id {edge_id!r}; snapshot ids must be unique")
        seen.add(edge_id)

        source_id = str(raw["source_id"])
        target_id = str(raw["target_id"])
        dangling = [i for i in (source_id, target_id) if i not in node_ids]
        if dangling:
            # A recursive adjacency query would walk straight off this edge and
            # return a path through a node the snapshot never described.
            _reject(
                f"edge {edge_id!r} names nodes absent from this snapshot: "
                + ", ".join(dangling)
            )

        confidence = str(raw.get("confidence") or "")
        if confidence not in CONFIDENCE_VALUES:
            _reject(
                f"edge {edge_id!r} has confidence {confidence!r}; expected one of "
                + ", ".join(sorted(CONFIDENCE_VALUES))
            )

        forbidden = _forbidden_in(raw.get("properties"))
        if forbidden:
            _reject(
                f"edge {edge_id!r} claims authority it cannot hold: "
                + ", ".join(forbidden)
                + ". Knowledge is evidence, never permission."
            )

        edges.append(
            {
                "edge_id": edge_id,
                "source_id": source_id,
                "target_id": target_id,
                "relation": str(raw["relation"]),
                "confidence": confidence,
                "properties": dict(raw.get("properties") or {}),
                "provenance": str(raw.get("provenance") or ""),
            }
        )
    return edges


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def snapshot_digest(document: Mapping[str, Any]) -> str:
    """A content digest over the parts that decide what gets projected.

    Deliberately excludes ``snapshot_id``, ``build_info`` and ``metadata``.
    ChaseOS mints a fresh ``snapshot_id`` for every extraction run and records
    timings and free-form notes alongside it, so including any of them would
    make the digest move on every rebuild of an unchanged corpus — which is
    precisely the question the digest exists to answer.

    Two snapshots with the same digest describe the same graph, whatever run
    produced them.
    """
    payload = {
        "vault_root": document.get("vault_root"),
        "extraction_scope": sorted(document.get("extraction_scope") or []),
        "nodes": sorted(
            (str(n.get("node_id")) for n in document.get("nodes") or [] if isinstance(n, Mapping))
        ),
        "edges": sorted(
            (str(e.get("edge_id")) for e in document.get("edges") or [] if isinstance(e, Mapping))
        ),
        "community_assignments": dict(
            sorted((document.get("community_assignments") or {}).items())
        ),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def summarise(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Counts the operator needs to see before trusting a projection."""
    nodes = snapshot.get("nodes") or []
    edges = snapshot.get("edges") or []

    by_type: dict[str, int] = {}
    by_confidence: dict[str, int] = {}
    for node in nodes:
        by_type[node["node_type"]] = by_type.get(node["node_type"], 0) + 1
        by_confidence[node["confidence"]] = by_confidence.get(node["confidence"], 0) + 1

    by_relation: dict[str, int] = {}
    for edge in edges:
        by_relation[edge["relation"]] = by_relation.get(edge["relation"], 0) + 1

    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "nodes_by_type": dict(sorted(by_type.items())),
        "nodes_by_confidence": dict(sorted(by_confidence.items())),
        "edges_by_relation": dict(sorted(by_relation.items())),
        # Stated so a reader of the projection cannot mistake it for canonical.
        "authority": "read_only_projection",
    }
