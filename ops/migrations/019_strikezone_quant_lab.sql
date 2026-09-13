-- UP
-- The StrikeZone quant lab inside Market Command: the closed-candle forward
-- test's signal ledger, its paper outcomes, and the documents the lab's jobs
-- rewrite (scorecards with regime cohorts, integrity health, methodology,
-- cost assumptions, and the fleet health state).
--
-- The lab runs in the Hermes fleet in WSL and writes plain JSON files. The
-- host bridge (tools/strikezone_quant_bridge.py) posts new ledger lines and
-- changed documents; charts are copied to a host folder mounted read-only.
-- TradeSync never writes to the lab and never runs a job. Every record is
-- paper-only research and carries no authority.
--
-- fleet_jobs gains the job's last error and last delivery error, so a
-- failing job says why on the dashboard instead of only in Discord.

create table if not exists sz_signals (
  signal_id text primary key,
  asset text not null,
  timeframe text not null,
  direction text not null check (direction in ('long', 'short', 'no_trade')),
  strategy_id text not null default '',
  strategy_version text not null default '',
  methodology_version text not null default '',
  signal_at timestamptz not null,
  candle_close_at timestamptz,
  expiry_at timestamptz,
  entry_price double precision,
  invalidation_price double precision,
  target_price double precision,
  confidence double precision,
  regime jsonb not null default '{}'::jsonb,
  analysis_eligible boolean not null default true,
  exclusion_reason text,
  ingested_at timestamptz not null default now()
);

create index if not exists idx_sz_signals_time on sz_signals(methodology_version, signal_at desc);
create index if not exists idx_sz_signals_pair on sz_signals(asset, timeframe, signal_at desc);

create table if not exists sz_outcomes (
  outcome_id text primary key,
  signal_id text not null,
  asset text not null,
  timeframe text not null,
  direction text not null,
  methodology_version text not null default '',
  exit_reason text,
  exit_at timestamptz,
  holding_minutes double precision,
  entry_fill_price double precision,
  exit_fill_price double precision,
  quantity double precision,
  gross_pnl_usdc double precision,
  net_pnl_usdc double precision,
  fees_usdc double precision,
  slippage_usdc double precision,
  funding_usdc double precision,
  funding_coverage text,
  correlation_group_id text,
  analysis_eligible boolean not null default true,
  ingested_at timestamptz not null default now()
);

create index if not exists idx_sz_outcomes_signal on sz_outcomes(signal_id);
create index if not exists idx_sz_outcomes_exit on sz_outcomes(methodology_version, exit_at);

create table if not exists sz_documents (
  kind text primary key check (kind in ('scorecards', 'health', 'methodology', 'assumptions', 'fleet_health')),
  payload jsonb not null,
  source_updated_at timestamptz,
  snapshot_at timestamptz not null default now()
);

alter table fleet_jobs add column if not exists last_error text;
alter table fleet_jobs add column if not exists last_delivery_error text;

-- DOWN
alter table fleet_jobs drop column if exists last_delivery_error;
alter table fleet_jobs drop column if exists last_error;
drop table if exists sz_documents;
drop table if exists sz_outcomes;
drop table if exists sz_signals;
