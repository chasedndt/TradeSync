-- UP
-- An operator's daily schedule for Hermes readings of the timeframe outlook, per
-- market and band (short term, lower, medium, higher time frame): an enabled flag
-- and a daily time in UTC. Off unless an operator turns it on: a band without a
-- row has no schedule, because Hermes compute is constrained. Every change keeps
-- an audit row with who made it, when, and the value it replaced. State-api's
-- schedule loop records the slot it last handled and what it did before it
-- starts anything, so a restart never starts the same slot twice.

create table if not exists horizon_reading_schedules (
  symbol text not null,
  scope text not null check (scope in ('short', 'lower', 'medium', 'higher')),
  enabled boolean not null default false,
  daily_time time not null,
  updated_by text not null,
  updated_at timestamptz not null default now(),
  last_slot timestamptz,
  last_result text,
  last_detail text,
  primary key (symbol, scope)
);

create table if not exists horizon_reading_schedule_audit (
  id uuid primary key default gen_random_uuid(),
  symbol text not null,
  scope text not null check (scope in ('short', 'lower', 'medium', 'higher')),
  changed_by text not null,
  changed_at timestamptz not null default now(),
  previous jsonb,
  next jsonb not null
);

create index if not exists idx_horizon_reading_schedule_audit_latest
  on horizon_reading_schedule_audit (symbol, scope, changed_at desc);

-- DOWN
drop table if exists horizon_reading_schedule_audit;
drop table if exists horizon_reading_schedules;
