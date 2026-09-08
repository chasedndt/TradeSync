-- UP
-- How long each pipeline stage has held its current state, and how often it
-- has changed. A state without a duration is half a fact: "scorer offline"
-- reads identically whether it dropped ten seconds ago or yesterday.
--
-- This is operational history, not market evidence. It informs the operator and
-- lets future alerting suppress a flapping stage; it carries no scoring or
-- approval authority.

create table if not exists node_state_history (
  id uuid primary key default gen_random_uuid(),
  node_id text not null,
  previous_state text,
  new_state text not null,
  entered_at timestamptz not null default now()
);

-- The common read is "current state of this node", which is the newest row.
create index if not exists idx_node_state_latest
  on node_state_history(node_id, entered_at desc);

-- DOWN
drop table if exists node_state_history;
