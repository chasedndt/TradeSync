-- UP
-- The Hermes fleet as Market Command sees it: jobs, runs, token usage, and
-- the operator's directives back to it.
--
-- The fleet lives in WSL; the host bridge reads its job registry, execution
-- ledger and usage audit and posts snapshots here, and applies directives
-- (schedule, enabled, working directory) to the registry with a backup on
-- every write. state-api never touches the fleet's files. A directive is
-- pending until the bridge reports it applied or failed, with what it
-- replaced, so any change can be reversed from the same panel.

create table if not exists fleet_jobs (
  job_id text primary key,
  name text not null,
  enabled boolean not null default true,
  schedule jsonb not null default '{}'::jsonb,
  schedule_display text not null default '',
  deliver text not null default 'local',
  workdir text,
  script text,
  no_agent boolean not null default false,
  model text,
  description text not null default '',
  last_run_at timestamptz,
  last_status text,
  next_run_at timestamptz,
  state text,
  snapshot_at timestamptz not null default now()
);

create table if not exists fleet_runs (
  id text primary key,
  job_id text not null,
  status text not null,
  claimed_at timestamptz,
  started_at timestamptz,
  finished_at timestamptz,
  duration_ms integer,
  error text,
  snapshot_at timestamptz not null default now()
);

create index if not exists idx_fleet_runs_job_time on fleet_runs(job_id, claimed_at desc);

create table if not exists fleet_usage (
  fire_id text primary key,
  job_id text not null,
  ts timestamptz not null,
  model text,
  prompt_tokens bigint not null default 0,
  completion_tokens bigint not null default 0,
  total_tokens bigint not null default 0,
  duration_ms integer,
  deliver_target text,
  response_silent boolean,
  error text
);

create index if not exists idx_fleet_usage_time on fleet_usage(ts desc);
create index if not exists idx_fleet_usage_job on fleet_usage(job_id, ts desc);

create table if not exists fleet_directives (
  id uuid primary key default gen_random_uuid(),
  job_id text not null,
  kind text not null check (kind in ('set_schedule', 'set_enabled', 'set_workdir')),
  payload jsonb not null,
  requested_by text not null default 'operator',
  requested_at timestamptz not null default now(),
  status text not null default 'pending' check (status in ('pending', 'applied', 'failed')),
  applied_at timestamptz,
  previous jsonb,
  detail text not null default ''
);

create index if not exists idx_fleet_directives_pending on fleet_directives(requested_at) where status = 'pending';

-- DOWN
drop table if exists fleet_directives;
drop table if exists fleet_usage;
drop table if exists fleet_runs;
drop table if exists fleet_jobs;
