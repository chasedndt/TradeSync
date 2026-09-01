# Knowledge Synchronization v1

`knowledge_sync_v1` defines the boundary between ChaseOS knowledge artifacts and TradeSync’s local read projection.

## Read direction: ChaseOS to TradeSync

The connector accepts a ChaseOS `GraphSnapshot` plus a synchronization envelope:

- `schema_version=knowledge_sync_v1`
- `snapshot_id`
- `snapshot_digest_sha256`
- `created_at`
- `extraction_scope[]`
- `producer_runtime`
- `producer_trust_tier`
- `node_count`, `edge_count`
- `artifact_uri` or bounded local path
- `promotion_receipt` when the snapshot contains promoted knowledge

Validation requires stable node/edge IDs, known confidence markers, provenance, referential integrity, supported schema, and digest match.

The accepted snapshot becomes a local read projection only. It does not transfer write or approval authority.

## Proposal direction: TradeSync to ChaseOS

TradeSync can produce a proposal package containing:

- source market evidence and authority class;
- decision/order/outcome IDs;
- candidate nodes/edges or lesson text;
- confidence and limitations;
- immutable payload digest;
- requested review/promotion action;
- target project/domain;
- expiry and supersession data.

The package enters ChaseOS quarantine/review. It never writes directly to promoted knowledge.

## Failure behavior

- incompatible or invalid snapshots stay staged and inactive;
- the prior verified projection remains readable with an explicit age indicator;
- no fresh approval is inferred from cached data;
- pending proposals remain in the local outbox;
- core TradeSync operation continues.

## Unverified seam

The public ChaseOS Core graph artifact was inspected and provides the snapshot model. The operator’s canonical private instance is currently unavailable, so actual private adapter discovery, live artifact path, authentication, and Gate endpoints remain unverified and must be reconciled before implementation is called connected.
