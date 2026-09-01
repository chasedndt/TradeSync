-- UP
-- Paper-shadow feature observations and normalization evidence. This migration
-- is authored for review and is not automatically applied by Docker Compose.

create table if not exists market_feature_catalogs (
  id uuid primary key default gen_random_uuid(),
  catalog_id text not null,
  version text not null,
  status text not null check (status in ('paper_shadow', 'paper_active', 'retired')),
  venue text not null check (venue = 'hyperliquid'),
  config_digest text not null unique,
  catalog jsonb not null,
  created_by text not null,
  created_at timestamptz not null default now(),
  unique(catalog_id, version)
);

create table if not exists market_feature_observations (
  id uuid primary key default gen_random_uuid(),
  feature_id text not null,
  symbol text not null,
  timeframe text not null,
  observed_at timestamptz not null,
  received_at timestamptz not null default now(),
  value double precision not null,
  unit text not null,
  provenance text not null check (provenance in ('observed', 'derived', 'proxy', 'context_only')),
  source_event_id text not null,
  source_payload_digest text,
  source_metadata jsonb not null default '{}'::jsonb,
  unique(feature_id, symbol, timeframe, observed_at, source_event_id)
);

create index if not exists idx_market_feature_history
  on market_feature_observations(feature_id, symbol, timeframe, observed_at desc);

create table if not exists market_feature_normalizations (
  id uuid primary key default gen_random_uuid(),
  observation_id uuid not null references market_feature_observations(id),
  catalog_record_id uuid not null references market_feature_catalogs(id),
  evaluated_at timestamptz not null,
  status text not null check (status in ('ready', 'stale', 'unavailable', 'not_normalized')),
  method text check (method in ('ordinary_zscore', 'robust_zscore')),
  history_start timestamptz,
  history_end timestamptz,
  history_count integer not null default 0 check (history_count >= 0),
  center double precision,
  dispersion double precision,
  mad double precision,
  z_score double precision,
  bounded_value double precision check (bounded_value between -1 and 1),
  score double precision check (score between -1 and 1),
  data_quality double precision not null check (data_quality between 0 and 1),
  scoring_allowed boolean not null default false,
  reason text,
  calculation jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(observation_id, catalog_record_id, method)
);

create index if not exists idx_market_feature_normalizations_replay
  on market_feature_normalizations(catalog_record_id, evaluated_at desc);

-- DOWN
drop table if exists market_feature_normalizations;
drop table if exists market_feature_observations;
drop table if exists market_feature_catalogs;
