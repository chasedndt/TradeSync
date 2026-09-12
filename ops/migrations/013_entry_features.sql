-- UP
-- What each candidate feature read at the moment a paper opportunity fired.
--
-- Slice 5 of the 2026-09-09 review sequence: evidence cards and earned
-- weights. A feature that enters the catalog as context-only (news tone,
-- the funding spread against Binance, the Coinbase premium before it was
-- admitted) can only earn a scoring weight by being measured against what
-- happened next. That needs its value *at entry*, recorded once and never
-- revised, because the live feature store keeps seven days and the signal
-- row keeps only the features that scored.
--
-- A NULL value is a real record: the store held no observation within the
-- feature's freshness tolerance at that moment, and the row says so, so the
-- job does not ask again. Rows are written by the core-scorer outcome job.

create table if not exists opportunity_entry_features (
  opportunity_id uuid not null references opportunities(id) on delete cascade,
  feature_id text not null,
  symbol text not null,
  value double precision,
  unit text not null default '',
  observed_at timestamptz,
  age_ms bigint,
  provenance text not null default '',
  source_authority text not null default '',
  scoring_eligible_at_entry boolean not null default false,
  catalog_version text not null default '',
  reason text not null default '',
  schema_version text not null default 'entry_feature_v1',
  recorded_at timestamptz not null default now(),
  primary key (opportunity_id, feature_id)
);

create index if not exists idx_entry_features_feature_symbol
  on opportunity_entry_features(feature_id, symbol);

-- DOWN
drop table if exists opportunity_entry_features;
