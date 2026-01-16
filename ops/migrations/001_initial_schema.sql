-- UP
create extension if not exists pgcrypto;
create extension if not exists "uuid-ossp";

create table if not exists events (
  id uuid primary key default gen_random_uuid(),
  v text not null default '0.1',
  ts timestamptz not null,
  source text not null,
  kind text not null,
  symbol text not null,
  timeframe text not null,
  payload jsonb not null,
  provenance jsonb not null default '{}'::jsonb,
  hash text not null unique,
  meta jsonb not null default '{}'::jsonb
);
create index if not exists idx_events_symbol_tf_ts on events(symbol, timeframe, ts);

create table if not exists signals (
  id uuid primary key default gen_random_uuid(),
  v text not null default '0.1',
  created_at timestamptz not null default now(),
  agent text not null,
  symbol text not null,
  timeframe text not null,
  kind text not null,
  confidence double precision not null check (confidence >= 0 and confidence <= 1),
  dir text not null,
  features jsonb not null default '{}'::jsonb,
  event_ids uuid[] not null default '{}',
  notes text not null default ''
);
create index if not exists idx_signals_symbol_tf_time on signals(symbol, timeframe, created_at);
create index if not exists idx_signals_agent_time on signals(agent, created_at);

create table if not exists opportunities (
  id uuid primary key default gen_random_uuid(),
  v text not null default '0.1',
  symbol text not null,
  timeframe text not null,
  snapshot_ts timestamptz not null default now(),
  expires_at timestamptz,
  bias double precision not null,
  quality double precision not null,
  confluence jsonb not null default '{}'::jsonb,
  dir text not null,
  links jsonb not null default '{}'::jsonb,
  status text not null default 'new'
);
create index if not exists idx_opps_symbol_tf_snap on opportunities(symbol, timeframe, snapshot_ts);

create table if not exists decisions (
  id uuid primary key default gen_random_uuid(),
  v text not null default '0.1',
  created_at timestamptz not null default now(),
  opportunity_id uuid not null references opportunities(id) on delete cascade,
  requested jsonb not null,
  risk jsonb not null
);
create index if not exists idx_decisions_opp_time on decisions(opportunity_id, created_at);

create table if not exists exec_orders (
  id uuid primary key default gen_random_uuid(),
  v text not null default '0.1',
  created_at timestamptz not null default now(),
  decision_id uuid not null references decisions(id) on delete cascade,
  venue text not null,
  request jsonb not null,
  response jsonb not null,
  status text not null default 'placed',
  txid text
);
create index if not exists idx_exec_decision on exec_orders(decision_id);

create table if not exists exposures (
  id uuid primary key default gen_random_uuid(),
  venue text not null,
  symbol text not null,
  size double precision not null default 0,
  notional double precision not null default 0,
  avg_entry double precision,
  updated_at timestamptz not null default now(),
  unique(venue, symbol)
);

create table if not exists regimes (
  id uuid primary key default gen_random_uuid(),
  symbol text not null,
  timeframe text not null,
  regime text not null,
  detected_at timestamptz not null default now()
);
create index if not exists idx_regimes_sym_tf_time on regimes(symbol, timeframe, detected_at);

create table if not exists calibration_params (
  id uuid primary key default gen_random_uuid(),
  agent text not null,
  regime text not null,
  method text not null,
  params jsonb not null,
  brier double precision,
  updated_at timestamptz not null default now(),
  unique(agent, regime)
);

create or replace view v_latest_opps as
  select distinct on (symbol, timeframe) *
  from opportunities
  order by symbol, timeframe, snapshot_ts desc;

-- DOWN
drop view if exists v_latest_opps;
drop table if exists calibration_params;
drop table if exists regimes;
drop table if exists exposures;
drop table if exists exec_orders;
drop table if exists decisions;
drop table if exists opportunities;
drop table if exists signals;
drop table if exists events;
drop extension if exists "uuid-ossp";
drop extension if exists pgcrypto;
