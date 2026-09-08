-- UP
-- Local adjacency projection of a ChaseOS GraphSnapshot.
--
-- ChaseOS is the canonical knowledge instance. This is a **projection**: every
-- row here is derived from a snapshot artifact and can be dropped and rebuilt
-- from it. TradeSync never writes canonical knowledge, and nothing in these
-- tables grants scoring, approval or execution authority — the exit gate for
-- this phase says so, and `graph_snapshot.py` refuses any node or edge that
-- carries a field claiming otherwise.
--
-- PostgreSQL rather than a graph database, per
-- `docs/architecture/DATA_AND_KNOWLEDGE_PLANE.md`: indexed adjacency plus
-- recursive CTEs covers the first use cases (strategy-to-rule lineage, evidence
-- paths, "why" explanations) without adding a fourth required runtime.

create table if not exists graph_snapshots (
  -- ChaseOS's own snapshot id, not a local surrogate: the projection has to be
  -- traceable back to the artifact it came from.
  snapshot_id text primary key,
  created_at timestamptz not null,
  vault_root text not null,
  extraction_scope jsonb not null default '[]'::jsonb,

  -- Over node and edge identity only. Build timings and free-form metadata are
  -- excluded, so re-extracting an unchanged corpus does not look like new
  -- knowledge.
  content_digest text not null,

  node_count integer not null check (node_count >= 0),
  edge_count integer not null check (edge_count >= 0),
  build_info jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,

  -- Exactly one projection is current. Older ones are kept: a graph is a claim
  -- about what was known at a time, and overwriting loses the ability to ask
  -- what the system believed when a decision was taken.
  ingested_at timestamptz not null default now(),
  superseded_at timestamptz
);

create table if not exists graph_nodes (
  snapshot_id text not null references graph_snapshots(snapshot_id) on delete cascade,
  -- Stable and content-derived by ChaseOS contract; unique within a snapshot.
  node_id text not null,

  label text not null,
  node_type text not null,
  source_file text not null,
  source_line integer,
  domain text,
  project text,
  properties jsonb not null default '{}'::jsonb,
  -- EXTRACTED | INFERRED | AMBIGUOUS. An INFERRED node is a heuristic result
  -- and must remain distinguishable from something directly observed.
  confidence text not null,
  provenance text not null default '',
  community_id integer,

  primary key (snapshot_id, node_id)
);

create table if not exists graph_edges (
  snapshot_id text not null references graph_snapshots(snapshot_id) on delete cascade,
  edge_id text not null,

  source_id text not null,
  target_id text not null,
  relation text not null,
  confidence text not null,
  properties jsonb not null default '{}'::jsonb,
  provenance text not null default '',

  primary key (snapshot_id, edge_id),
  -- Enforced in the database as well as in the validator. A dangling edge would
  -- let a recursive query return a path through a node the snapshot never
  -- described, with the same confidence as a real one.
  foreign key (snapshot_id, source_id) references graph_nodes(snapshot_id, node_id)
    on delete cascade,
  foreign key (snapshot_id, target_id) references graph_nodes(snapshot_id, node_id)
    on delete cascade
);

-- Adjacency in both directions: "what does this reference" and "what references
-- this" are both first-class questions, and a recursive CTE walking backwards
-- without an index degrades to a scan per level.
create index if not exists idx_graph_edges_out
  on graph_edges (snapshot_id, source_id, relation);
create index if not exists idx_graph_edges_in
  on graph_edges (snapshot_id, target_id, relation);

create index if not exists idx_graph_nodes_type
  on graph_nodes (snapshot_id, node_type);
create index if not exists idx_graph_nodes_source
  on graph_nodes (snapshot_id, source_file);
-- Label lookup is how a human enters the graph; without this it is a scan over
-- every node in the snapshot.
create index if not exists idx_graph_nodes_label
  on graph_nodes (snapshot_id, lower(label));

create index if not exists idx_graph_snapshots_current
  on graph_snapshots (ingested_at desc) where superseded_at is null;

-- DOWN
drop index if exists idx_graph_snapshots_current;
drop index if exists idx_graph_nodes_label;
drop index if exists idx_graph_nodes_source;
drop index if exists idx_graph_nodes_type;
drop index if exists idx_graph_edges_in;
drop index if exists idx_graph_edges_out;
drop table if exists graph_edges;
drop table if exists graph_nodes;
drop table if exists graph_snapshots;
