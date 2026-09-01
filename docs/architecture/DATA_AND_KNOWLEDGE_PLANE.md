# Data and Knowledge Plane

## Decision summary

TradeSync uses a polyglot data plane with one clear authority per concern:

- PostgreSQL for durable operational truth;
- Redis Streams for real-time transport and short-lived state;
- Qdrant for rebuildable semantic retrieval;
- content-addressed files on E: for immutable raw artifacts;
- ChaseOS `GraphSnapshot` JSON as the canonical knowledge-graph artifact.

This gives fast agent access without allowing an embedding index, cache, or model to become a source of authority.

## Why PostgreSQL is the initial graph projection

ChaseOS Core defines the graph artifact as deterministic nodes and edges with stable IDs, confidence, provenance, snapshot metadata, and derived indexes. TradeSync should ingest verified snapshots into local adjacency tables:

- `knowledge_snapshots`
- `knowledge_nodes`
- `knowledge_edges`
- `knowledge_sync_receipts`
- `knowledge_proposals`

PostgreSQL supports indexed adjacency queries and recursive common-table expressions. That is adequate for the first graph use cases: strategy-to-rule lineage, evidence paths, asset/timeframe relationships, and “why” explanations. It also avoids adding Neo4j as a fourth required runtime.

Add a dedicated graph database only if measured production queries exceed agreed latency/complexity limits after indexing, caching, and query-shape improvements.

## Time-series strategy

Current truth:

- Compose uses `postgres:16`, not a TimescaleDB image.
- `TimescaleStore` exists only as an unimplemented placeholder.
- Some current market history lives in Redis.

Plan:

1. move durable candles, funding, OI, book summaries, trades, regime states, and alert events to PostgreSQL;
2. use native range partitioning by event/candle time and indexes by `(symbol, timeframe, observed_at)`;
3. benchmark ingestion, retention, common chart queries, and journal joins;
4. adopt TimescaleDB only if benchmarks show a meaningful operational benefit and migration/backup tests pass.

Documentation must not claim TimescaleDB is active until its image, migrations, store implementation, tests, backups, and runtime verification exist.

## Real-time path

1. Hyperliquid edge normalizes public WebSocket/HTTP messages.
2. The event receives an immutable ID, source timestamp, receipt timestamp, authority class, and raw-payload digest.
3. Redis Streams distributes the event to regime, scorer, fusion, journal, and alert consumers.
4. A persistence consumer writes the event once to PostgreSQL.
5. Consumers commit durable outputs before acknowledging the stream message.
6. On restart, consumer groups reclaim pending messages; database uniqueness constraints prevent duplicates.

Redis loss can delay real-time work but cannot erase already committed truth.

## Knowledge synchronization

The initial ChaseOS connector is snapshot-based and read-only:

1. discover a `GraphSnapshot` artifact through a configured adapter;
2. verify schema, snapshot ID, scope, digest, timestamps, node/edge IDs, confidence, and provenance;
3. stage it as `received`;
4. build a transactionally consistent local PostgreSQL projection;
5. mark it `active_read_projection` only after validation;
6. asynchronously update Qdrant from approved/promoted nodes;
7. retain the previous verified projection for rollback;
8. report connector age and compatibility in the Cockpit.

TradeSync writeback produces proposals/evidence packages. It does not directly mutate `02_KNOWLEDGE`. ChaseOS promotion remains an explicit Gate-controlled operation.

## Agent query path

Agent harnesses use a bounded query service, not raw database credentials:

- exact filters and joins query PostgreSQL;
- semantic candidate retrieval queries Qdrant;
- the service resolves semantic hits back to canonical node/evidence IDs;
- every result includes snapshot ID, source path, confidence, provenance, and freshness;
- responses are advisory unless a deterministic policy independently validates them;
- action requests go through the approval and execution contracts.

## Retention classes

| Class | Examples | Storage |
|---|---|---|
| Hot | latest market state, active alerts, pending decisions | Redis plus PostgreSQL |
| Warm | candles, regimes, opportunities, journal, outcomes | PostgreSQL partitions |
| Semantic | promoted knowledge chunks and approved evidence | Qdrant, rebuildable |
| Artifact | raw documents, graph snapshots, receipts, exports | Content-addressed files on E: |
| Secret | signing keys, tokens, VAPID private key | Governed secret store only; never the data plane |

## Relevant references

- ChaseOS Core graph artifact source inspected locally at `C:\Users\chaseos\Documents\Projects\chaseos-core\runtime\graph\artifact.py`.
- [PostgreSQL recursive queries](https://www.postgresql.org/docs/current/queries-with.html)
- [PostgreSQL table partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html)
- [Qdrant collections](https://qdrant.tech/documentation/concepts/collections/)

## Canonical diagram

Source: [data-knowledge-plane.mmd](../diagrams/data-knowledge-plane.mmd)
