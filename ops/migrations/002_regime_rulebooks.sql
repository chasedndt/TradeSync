-- UP
-- Authored for the versioned Regime Rulebook foundation. This migration is
-- intentionally not applied automatically by Docker Compose.

create table if not exists regime_rulebooks (
  id uuid primary key default gen_random_uuid(),
  rulebook_id text not null,
  version text not null,
  schema_version text not null,
  status text not null check (status in ('draft', 'paper_active', 'retired')),
  environment text not null check (environment = 'paper'),
  horizon text not null,
  parent_id uuid references regime_rulebooks(id),
  config_digest text not null unique,
  config jsonb not null,
  created_by text not null,
  created_at timestamptz not null default now(),
  unique(rulebook_id, horizon, version)
);

create index if not exists idx_regime_rulebooks_identity
  on regime_rulebooks(rulebook_id, horizon, created_at desc);

create table if not exists regime_weight_activations (
  id uuid primary key default gen_random_uuid(),
  regime_rulebook_id uuid not null references regime_rulebooks(id),
  horizon text not null,
  environment text not null check (environment = 'paper'),
  activated_by text not null,
  approval_reference text,
  activated_at timestamptz not null default now(),
  deactivated_at timestamptz,
  check (deactivated_at is null or deactivated_at >= activated_at)
);

create unique index if not exists uq_active_regime_rulebook
  on regime_weight_activations(horizon, environment)
  where deactivated_at is null;

create table if not exists regime_experiments (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  status text not null check (status in ('draft', 'running', 'completed', 'rejected', 'promoted')),
  horizon text not null,
  champion_rulebook_id uuid not null references regime_rulebooks(id),
  challenger_rulebook_id uuid not null references regime_rulebooks(id),
  hypothesis text not null,
  evaluation_plan jsonb not null,
  results jsonb,
  started_at timestamptz,
  ended_at timestamptz,
  created_at timestamptz not null default now(),
  check (champion_rulebook_id <> challenger_rulebook_id),
  check (ended_at is null or started_at is not null),
  check (ended_at is null or ended_at >= started_at)
);

create table if not exists regime_score_events (
  id uuid primary key default gen_random_uuid(),
  observed_at timestamptz not null,
  recorded_at timestamptz not null default now(),
  symbol text not null,
  timeframe text not null,
  regime_rulebook_id uuid not null references regime_rulebooks(id),
  rulebook_version text not null,
  config_digest text not null,
  source_event_ids uuid[] not null default '{}',
  block_inputs jsonb not null,
  data_quality jsonb not null,
  contributions jsonb not null,
  risk_flags jsonb not null default '[]'::jsonb,
  weighted_score double precision not null check (weighted_score between -1 and 1),
  data_coverage double precision not null check (data_coverage between 0 and 1),
  paper_risk_multiplier double precision not null check (paper_risk_multiplier between 0 and 1),
  playbook_permissions jsonb not null default '{}'::jsonb
);

create index if not exists idx_regime_score_events_replay
  on regime_score_events(symbol, timeframe, observed_at desc);

create index if not exists idx_regime_score_events_rulebook
  on regime_score_events(regime_rulebook_id, observed_at desc);

-- DOWN
drop table if exists regime_score_events;
drop table if exists regime_experiments;
drop index if exists uq_active_regime_rulebook;
drop table if exists regime_weight_activations;
drop table if exists regime_rulebooks;
