-- UP
-- The market outlook frozen with each thesis edition, and the Hermes link.
--
-- An edition now carries, beside the per-symbol theses, the outlook the
-- operator reads first: overall direction across the tracked universe, the
-- week's scheduled events with how the market measurably reacted to past
-- occurrences of each, recent articles on them, and an advisory briefing
-- drafted by Hermes through the harness boundary. ``reason`` records why an
-- operator regenerated the thesis (a black-swan event, a mid-session reset).
--
-- ``hermes_gateway_state`` holds the last gateway state file the host bridge
-- read (platform states, pid, version), so the dashboard can say whether the
-- Discord platform or the API server is the part that is down.

alter table thesis_editions add column if not exists outlook jsonb not null default '{}'::jsonb;
alter table thesis_editions add column if not exists briefing jsonb not null default '{}'::jsonb;
alter table thesis_editions add column if not exists reason text not null default '';

create table if not exists hermes_gateway_state (
  id smallint primary key default 1 check (id = 1),
  payload jsonb not null default '{}'::jsonb,
  source_updated_at timestamptz,
  snapshot_at timestamptz not null default now()
);

-- DOWN
drop table if exists hermes_gateway_state;
alter table thesis_editions drop column if exists reason;
alter table thesis_editions drop column if exists briefing;
alter table thesis_editions drop column if exists outlook;
