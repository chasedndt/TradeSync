# DOC_PROMPTS.md
Purpose: explain how to use prompt packs in /prompts/* to scaffold TradeSync to spec.
See folders:
- prompts/shared, /windsurf, /claude, /cursor
- prompts/scaffolds, /agents, /tests, /ops
Follow global guardrails and acceptance checklist from this doc.
"
# === 0) Point to your repo root ===
C:\TradeSync = "C:\TradeSync"

 = Join-Path C:\TradeSync "prompts"
 = Join-Path C:\TradeSync "docs\PROMPTS"

# --- 1) Ensure destination exists
New-Item -ItemType Directory -Force -Path  | Out-Null

# --- 2) Move *contents* of prompts/ into docs/PROMPTS/
if (Test-Path ) {
  Get-ChildItem -Path  -Force | ForEach-Object {
    Move-Item -LiteralPath .FullName -Destination  -Force
  }
  Write-Host "Moved contents of 'prompts/' -> 'docs/PROMPTS/'"
} else {
  Write-Host "Source folder not found: "
}

# --- 3) Remove empty prompts/ (if it exists and is now empty)
if (Test-Path ) {
  if ((Get-ChildItem -LiteralPath  -Force | Measure-Object).Count -eq 0) {
    Remove-Item -LiteralPath  -Force
    Write-Host "Removed empty folder: "
  } else {
    Write-Host "NOTE: '' not empty; inspect manually."
  }
}

# --- 4) Update references in docs/*.md from 'prompts/' -> 'docs/PROMPTS/'
 = Get-ChildItem -Path (Join-Path C:\TradeSync "docs") -Recurse -Include *.md -File
foreach ( in ) {
  (Get-Content .FullName -Raw) 
    -replace '(?<![A-Za-z0-9_/])prompts/', 'docs/PROMPTS/' 
  | Set-Content .FullName -Encoding UTF8
  Write-Host "Updated refs in "
}

# --- 5) Quick verify
Write-Host "
=== New tree under docs/PROMPTS ==="
Get-ChildItem -Path  -Recurse | Select-Object FullName




C:\TradeSync = "C:\TradeSync"
  = Join-Path C:\TradeSync "docs\DOC_PROMPTS.md"
  = ".bak"

Copy-Item -LiteralPath  -Destination  -Force

# Replace all 'prompts/' links with 'docs/PROMPTS/'
(Get-Content  -Raw) -replace '(?<![A-Za-z0-9_/])prompts/', 'docs/PROMPTS/' |
  Set-Content  -Encoding UTF8

Write-Host "Updated links in DOC_PROMPTS.md. Backup at: "

# === Set your repo root ===
C:\TradeSync = "C:\TradeSync"

# Ensure folders
New-Item -ItemType Directory -Force -Path (Join-Path C:\TradeSync "ops\sql") | Out-Null

function Write-Text(, ) {
   = Join-Path C:\TradeSync 
  New-Item -ItemType File -Force -Path  | Out-Null
  Set-Content -Path  -Value  -Encoding UTF8
  Write-Host "Wrote "
}

# === schema.sql (Postgres) ===
Write-Text "ops\sql\schema.sql" @"
-- TradeSync DB schema (matches AGENT_INTERFACE + ERD)
create extension if not exists pgcrypto;   -- for gen_random_uuid()
create extension if not exists "uuid-ossp";

-- Core: events (normalized), signals, opportunities, decisions, exec orders
create table if not exists events (
  id uuid primary key default gen_random_uuid(),
  v text not null default '0.1',
  ts timestamptz not null,
  source text not null,                                 -- tv|yt|metrics|discord
  kind text not null,                                   -- tv|yt_chunk|idea|funding|oi_delta|liqmap
  symbol text not null,
  timeframe text not null,
  payload jsonb not null,
  provenance jsonb not null default '{}'::jsonb,
  hash text not null unique,                            -- idempotency hash
  meta jsonb not null default '{}'::jsonb
);
create index if not exists idx_events_symbol_tf_ts on events(symbol, timeframe, ts);

create table if not exists signals (
  id uuid primary key default gen_random_uuid(),
  v text not null default '0.1',
  created_at timestamptz not null default now(),
  agent text not null,                                  -- tech|funding|sentiment|rotation
  symbol text not null,
  timeframe text not null,
  kind text not null,                                   -- trend|squeeze_risk|...
  confidence double precision not null check (confidence >= 0 and confidence <= 1),
  dir text not null,                                    -- long|short|neutral
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
  bias double precision not null,                       -- 0..1 long-bias
  quality double precision not null,                    -- fusion quality
  confluence jsonb not null default '{}'::jsonb,        -- {tech:0.7, funding:0.6,...}
  dir text not null,                                    -- long|short
  links jsonb not null default '{}'::jsonb,             -- {event_ids:[], urls:[]}
  status text not null default 'new'                    -- new|previewed|executed|blocked|expired
);
create index if not exists idx_opps_symbol_tf_snap on opportunities(symbol, timeframe, snapshot_ts);

create table if not exists decisions (
  id uuid primary key default gen_random_uuid(),
  v text not null default '0.1',
  created_at timestamptz not null default now(),
  opportunity_id uuid not null references opportunities(id) on delete cascade,
  requested jsonb not null,                             -- venue,size,dir,plan{entry,sl,tp}
  risk jsonb not null                                   -- allowed, reason_code, checks{...}
);
create index if not exists idx_decisions_opp_time on decisions(opportunity_id, created_at);

create table if not exists exec_orders (
  id uuid primary key default gen_random_uuid(),
  v text not null default '0.1',
  created_at timestamptz not null default now(),
  decision_id uuid not null references decisions(id) on delete cascade,
  venue text not null,                                  -- drift|hyperliquid
  request jsonb not null,
  response jsonb not null,
  status text not null default 'placed',
  txid text
);
create index if not exists idx_exec_decision on exec_orders(decision_id);

-- Risk/exposure & regime detection
create table if not exists exposures (
  id uuid primary key default gen_random_uuid(),
  venue text not null,                                  -- drift|hyperliquid
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
  regime text not null,                                 -- trend|range|high_vol|low_vol
  detected_at timestamptz not null default now()
);
create index if not exists idx_regimes_sym_tf_time on regimes(symbol, timeframe, detected_at);

create table if not exists calibration_params (
  id uuid primary key default gen_random_uuid(),
  agent text not null,
  regime text not null,
  method text not null,                                 -- isotonic|platt|temp
  params jsonb not null,
  brier double precision,
  updated_at timestamptz not null default now()
);
create unique index if not exists uq_calib_agent_regime on calibration_params(agent, regime);

-- Views/helpers (optional)
create or replace view v_latest_opps as
  select distinct on (symbol, timeframe) *
  from opportunities
  order by symbol, timeframe, snapshot_ts desc;
