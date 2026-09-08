# Slot 3.4 — read-only ChaseOS graph-snapshot adapter and PostgreSQL projection

Date: 2026-09-08
Scope: `libs/tradesync_core/graph_snapshot.py`,
`ops/migrations/009_chaseos_graph_projection.sql`,
`services/state-api/app/graph_projection.py`, `services/state-api/app/main.py`,
`ops/compose.market-command.yml`

## What this is

The roadmap's Week 2 line: *"Implement a read-only ChaseOS graph-snapshot
adapter and a local PostgreSQL graph projection."* ChaseOS remains the canonical
knowledge instance. TradeSync reads its snapshot artifacts and keeps a local
adjacency copy so lineage and "why does this rule exist" can be answered without
a network call — and so the system keeps working when the connector is off.

## What already existed, and what did not

ChaseOS defines the artifact at `chaseos-core/runtime/graph/artifact.py`:
`GraphSnapshot` with deterministic content-derived node and edge ids, a
confidence marker (`EXTRACTED` / `INFERRED` / `AMBIGUOUS`), provenance, and
community assignments. That contract was read, not reinvented.

`.chaseos/graph/` in the canonical vault is **empty** — ChaseOS has not written
a snapshot there. Rather than stop at a fixture, ChaseOS's own
`runtime/graph/builder.py` was run against the real vault and the result written
to a TradeSync-side directory. The vault is read; `.chaseos/graph/` is ChaseOS's
to write, and TradeSync's whole boundary is that it does not write canonical
knowledge.

**Real snapshot, real projection.** 7,314 nodes and 10,123 edges across 307
communities, built in 8.5s by ChaseOS's own code, ingested in 6.3s:

```
node types  doc_section=197, file=217, frontmatter_key=5, manifest_field=167,
            python_class=231, python_function=3391, python_import=2676,
            wikilink_ref=395, workflow=35
relations   defines=3580, file_contains=3206, imports=2676, inherits=69,
            references=425, workflow_declares=167
```

Adjacency on a real hub — `runtime/cli/main.py`, degree 1520 — answers in 36ms
at depth 1 and 41ms at depth 3.

That last figure exposed something worth fixing. Results are ordered
nearest-first, so a hub fills the whole limit at one hop and a depth-3 request
returns nothing from hops 2 or 3. `truncated` said something was cut but not
what you were looking at, so the response now carries `hops_returned` and
`reached_requested_depth`. A number that quietly means less than it appears to
is the failure mode this whole system is built against.

## The boundaries, enforced rather than documented

**Read-only, structurally.** Every filesystem call in `graph_projection.py`
opens a file for reading. There is no write path to the vault at all. The
compose mount is `:ro` on top of that, and it is proven:

```
$ docker exec tradesync-full-state-api-1 touch /knowledge/chaseos-graph/write-probe
touch: cannot touch '/knowledge/chaseos-graph/write-probe': Read-only file system
```

**No authority.** A node or edge carrying `execution_authority`, `approved`,
`scoring_allowed`, `tier`, `trust` or any of the other `FORBIDDEN_FIELDS` is
**refused by name**, not stripped and accepted. A connector trying to grant
itself authority is not a formatting problem, and quietly cleaning it up would
hide the attempt. Same list and same threat model as the quarantine intake path.

**Referential integrity.** An edge whose endpoints are not both present is
refused, and the database has matching composite foreign keys. Projecting one
would let a recursive query return a path through a node the snapshot never
described, with the same confidence as a real one.

**Off by default.** `CHASEOS_GRAPH_DIR` is unset unless the operator sets it. A
knowledge connector that switches itself on because a path happens to exist is a
connector the operator did not choose to run.

## Two defects found while verifying

**A malformed `created_at` escaped as HTTP 500.** It was parsed at projection
time, outside the endpoint's `SnapshotRejected` handling. It is a contract
violation like any other; it now lives in `validate_snapshot` and answers 422
with a reason the operator can take back to ChaseOS. An unparseable timestamp is
never replaced with `now()` — that would date the snapshot to when TradeSync read
it, not when the knowledge was extracted.

**The content digest included `snapshot_id`.** ChaseOS mints a fresh id for
every extraction run, so the digest moved on every rebuild whether or not the
corpus changed — defeating the exact question it exists to answer. Now
content-only. Proven: the same corpus under two different run ids produces
`922ea26ec6ee61c5` both times.

## Verified

Fixture: 2,800 nodes, 9,600 edges, 3.7 MB, built with ChaseOS's own model,
including deliberate cycles because real vaults are full of them.

```
ingested in 2.7s
 nodes 2800 edges 9600 | authority read_only_projection
 by type       {'doc_section': 2400, 'file': 400}
 by confidence {'EXTRACTED': 2000, 'INFERRED': 800}
 by relation   {'file_contains': 2400, 'references': 7200}

depth 1: 7 nodes in 23ms
depth 2: 33 nodes in 10ms
depth 3: 95 nodes in 16ms
```

The recursive walk carries its path in `visited` so a cycle terminates; without
that a cross-referencing knowledge graph does not return.

Every refusal path answers with a stated reason:

| case | status | answer |
|---|---|---|
| node claims `execution_authority` | 422 | names the field, "Knowledge is evidence, never permission." |
| edge to an absent node | 422 | names the missing node |
| confidence `TRUSTED` | 422 | names the accepted vocabulary |
| `created_at: "last Tuesday"` | 422 | not ISO 8601 |
| not JSON at all | 400 | unreadable snapshot |
| no such file | 404 | names it |
| unknown node id | 404 | names the snapshot searched |
| `depth=5` | 422 | capped at 4 |

Superseding rather than overwriting: ingesting a second snapshot leaves the
first in place, marked superseded. A decision taken last week was taken against
the graph of last week.

**Exit gate — "TradeSync remains fully usable with every optional connector
disabled."** With `CHASEOS_GRAPH_DIR` unset, the status endpoint answers
`not_configured` (200, not an error) and `/healthz`, `/state/opportunities`,
`/state/market/candles`, `/state/market/context` and
`/state/integration-pipeline` all answer 200.

Tests: 34 in `tests/test_graph_snapshot.py`, including one per forbidden field
on both nodes and edges. Full suite 459 passing.

## Enabling it

Point at wherever snapshots are built. `dashboard-runtime/chaseos-graph` holds
the one built on 2026-09-08; `.chaseos/graph` inside the vault is the natural
home once ChaseOS writes there itself.

```
CHASEOS_GRAPH_HOST_DIR=E:/Projects/TradeSync/dashboard-runtime/chaseos-graph
CHASEOS_GRAPH_DIR=/knowledge/chaseos-graph
```

Rebuild the snapshot with ChaseOS's own builder rather than anything here:
`build_snapshot(vault_root)` then `save_snapshot(snapshot, output_dir)` from
`chaseos-core/runtime/graph/builder.py`.

Then `POST /state/knowledge/graph/ingest`. Read with
`/state/knowledge/graph/status`, `/nodes`, and `/neighbours/{node_id}`.

## What is still outstanding for Slot 3.4

The ChaseOS **Gate** — approval authority — is not part of this. This slice is
the knowledge half: read a snapshot, project it, answer questions about it. No
model or connector can write canonical knowledge or consume approval authority,
which is the exit gate; granting approval is a separate mechanism and is not
implemented.
