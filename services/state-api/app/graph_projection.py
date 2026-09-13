"""Read a ChaseOS GraphSnapshot from disk and project it locally.

**Read-only, structurally.** Every filesystem call in this module opens a file
for reading. There is no write path to the vault, and the configured directory
is never created, listed for writing, or modified. That is the roadmap's exit
gate for this phase — "no model or connector can write canonical ChaseOS
knowledge or consume approval authority" — expressed as an absence of code
rather than as a promise.

The projection is derived data. Dropping every row and re-ingesting the same
artifact reproduces it exactly, which is why the artifact and not the projection
is the thing to trust.

TradeSync must stay fully usable with this connector disabled. Nothing here is
called on a request path that matters, and a missing or unreadable snapshot
directory is an ordinary "not configured" answer, not an error.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from tradesync_core.graph_snapshot import (
    SnapshotRejected,
    parse_created_at,
    summarise,
    validate_snapshot,
)

logger = logging.getLogger(__name__)

# Unset by default. A knowledge connector that switches itself on because a path
# happens to exist is a connector the operator did not choose to run.
CHASEOS_GRAPH_DIR = os.getenv("CHASEOS_GRAPH_DIR", "").strip()

# A snapshot of a 27k-note vault is large but bounded. This refuses a file big
# enough to be a mistake before parsing it into memory.
MAX_SNAPSHOT_BYTES = int(os.getenv("CHASEOS_GRAPH_MAX_BYTES", str(256 * 1024 * 1024)))
# Seven thousand nodes and ten thousand edges through executemany exceeds the
# pool's default statement timeout on a loaded host (2026-09-13). The
# projection is one transaction, so a bounded but generous limit is right.
PROJECT_TIMEOUT_S = float(os.getenv("CHASEOS_GRAPH_PROJECT_TIMEOUT_S", "900"))


def snapshot_directory() -> Path | None:
    return Path(CHASEOS_GRAPH_DIR) if CHASEOS_GRAPH_DIR else None


def available_snapshots() -> list[Path]:
    """Snapshot files in the configured directory, newest first.

    Returns an empty list rather than raising when nothing is configured: an
    offline optional connector is a normal state for this system.
    """
    directory = snapshot_directory()
    if directory is None or not directory.is_dir():
        return []
    files = [p for p in directory.glob("*.json") if p.is_file()]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def read_snapshot(path: Path) -> dict[str, Any]:
    """Load and validate one snapshot file.

    Opened read-only. Refuses before parsing if the file is implausibly large,
    so a wrong path cannot exhaust memory.
    """
    size = path.stat().st_size
    if size > MAX_SNAPSHOT_BYTES:
        raise SnapshotRejected(
            f"{path.name} is {size} bytes, over the {MAX_SNAPSHOT_BYTES} limit"
        )
    with path.open("r", encoding="utf-8") as handle:
        document = json.load(handle)
    return validate_snapshot(document)


async def project_snapshot(conn, snapshot: dict[str, Any]) -> dict[str, Any]:
    """Write one validated snapshot into the adjacency tables.

    Whole or not at all, in one transaction. A half-projected graph answers
    adjacency questions *wrongly* rather than refusing to answer them, which is
    strictly worse than having no projection.

    Re-ingesting the same ``snapshot_id`` replaces its rows. Earlier snapshots
    are marked superseded rather than deleted: a graph is a claim about what was
    known at a time, and a decision taken last week was taken against the graph
    of last week.
    """
    nodes = snapshot["nodes"]
    edges = snapshot["edges"]
    communities = snapshot["community_assignments"]
    # Guaranteed to parse: validate_snapshot refused the snapshot otherwise.
    created_at = parse_created_at(snapshot["created_at"])

    async with conn.transaction():
        # Cascades to this snapshot's own nodes and edges; leaves other
        # snapshots untouched.
        await conn.execute(
            "DELETE FROM graph_snapshots WHERE snapshot_id = $1",
            snapshot["snapshot_id"],
        )
        await conn.execute(
            """
            UPDATE graph_snapshots SET superseded_at = now()
            WHERE superseded_at IS NULL
            """
        )
        await conn.execute(
            """
            INSERT INTO graph_snapshots (
                snapshot_id, created_at, vault_root, extraction_scope,
                content_digest, node_count, edge_count, build_info, metadata
            ) VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8::jsonb, $9::jsonb)
            """,
            snapshot["snapshot_id"],
            created_at,
            snapshot["vault_root"],
            json.dumps(snapshot["extraction_scope"]),
            snapshot["content_digest"],
            len(nodes),
            len(edges),
            json.dumps(snapshot["build_info"]),
            json.dumps(snapshot["metadata"]),
        )

        # Nodes before edges: the edge foreign keys require both endpoints to
        # exist, which is the database enforcing what the validator checked.
        await conn.executemany(
            """
            INSERT INTO graph_nodes (
                snapshot_id, node_id, label, node_type, source_file, source_line,
                domain, project, properties, confidence, provenance, community_id
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11,$12)
            """,
            [
                (
                    snapshot["snapshot_id"],
                    n["node_id"],
                    n["label"],
                    n["node_type"],
                    n["source_file"],
                    n["source_line"],
                    n["domain"],
                    n["project"],
                    json.dumps(n["properties"]),
                    n["confidence"],
                    n["provenance"],
                    communities.get(n["node_id"]),
                )
                for n in nodes
            ],
            timeout=PROJECT_TIMEOUT_S,
        )
        await conn.executemany(
            """
            INSERT INTO graph_edges (
                snapshot_id, edge_id, source_id, target_id, relation,
                confidence, properties, provenance
            ) VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8)
            """,
            [
                (
                    snapshot["snapshot_id"],
                    e["edge_id"],
                    e["source_id"],
                    e["target_id"],
                    e["relation"],
                    e["confidence"],
                    json.dumps(e["properties"]),
                    e["provenance"],
                )
                for e in edges
            ],
            timeout=PROJECT_TIMEOUT_S,
        )

    return {
        "snapshot_id": snapshot["snapshot_id"],
        "content_digest": snapshot["content_digest"],
        **summarise(snapshot),
    }


async def current_snapshot(conn) -> dict[str, Any] | None:
    """The projection in force, or None when the connector has never run."""
    row = await conn.fetchrow(
        """
        SELECT snapshot_id, created_at, vault_root, content_digest,
               node_count, edge_count, ingested_at, extraction_scope, build_info
        FROM graph_snapshots
        WHERE superseded_at IS NULL
        ORDER BY ingested_at DESC LIMIT 1
        """
    )
    return dict(row) if row else None


async def neighbours(
    conn, snapshot_id: str, node_id: str, depth: int, limit: int
) -> list[dict[str, Any]]:
    """Nodes reachable from ``node_id`` within ``depth`` hops, either direction.

    The walk is undirected because the questions this exists to answer —
    lineage, evidence paths, "why does this rule exist" — do not care which way
    the extractor happened to orient an edge.

    ``visited`` carries the path so a cycle terminates. A knowledge graph
    extracted from cross-referencing documents is full of them, and a recursive
    CTE without cycle detection does not return.
    """
    rows = await conn.fetch(
        """
        WITH RECURSIVE walk AS (
            SELECT n.node_id, n.label, n.node_type, n.source_file, n.confidence,
                   0 AS hops, ARRAY[n.node_id] AS visited, NULL::text AS via
            FROM graph_nodes n
            WHERE n.snapshot_id = $1 AND n.node_id = $2

            UNION ALL

            SELECT n.node_id, n.label, n.node_type, n.source_file, n.confidence,
                   w.hops + 1, w.visited || n.node_id, e.relation
            FROM walk w
            JOIN graph_edges e
              ON e.snapshot_id = $1
             AND (e.source_id = w.node_id OR e.target_id = w.node_id)
            JOIN graph_nodes n
              ON n.snapshot_id = $1
             AND n.node_id = CASE WHEN e.source_id = w.node_id
                                  THEN e.target_id ELSE e.source_id END
            WHERE w.hops < $3
              AND NOT n.node_id = ANY(w.visited)
        )
        SELECT node_id, label, node_type, source_file, confidence,
               min(hops) AS hops, min(via) AS via
        FROM walk
        GROUP BY node_id, label, node_type, source_file, confidence
        ORDER BY min(hops), label
        LIMIT $4
        """,
        snapshot_id,
        node_id,
        depth,
        limit,
    )
    return [dict(row) for row in rows]
