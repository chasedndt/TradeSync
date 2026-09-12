-- UP
-- Claims extracted from quarantined material, and what happened after them.
--
-- A Pine alert, an agent's Discord post or a Hermes job output is untrusted
-- text. Extraction turns each into zero or more *claims*: this source said
-- this direction on this symbol at this time. A claim is then measured the
-- way a paper opportunity is measured (forward return at 15/60/240 minutes
-- from venue candles), so every source accumulates a track record and the
-- source cards can say whether it has earned a weight.
--
-- Extraction is recorded per quarantine row even when it yields nothing, so
-- the job never re-reads a row and the operator can see why a post produced
-- no claim. Nothing here confers authority; a claim is not a signal.

create table if not exists quarantine_extractions (
  quarantine_id uuid primary key references quarantine_intake(id) on delete cascade,
  extractor text not null,
  claims integer not null default 0,
  reason text not null default '',
  extracted_at timestamptz not null default now()
);

create table if not exists evidence_claims (
  id uuid primary key default gen_random_uuid(),
  quarantine_id uuid not null references quarantine_intake(id) on delete cascade,
  source text not null,
  source_id text not null,
  symbol text not null,
  direction text not null check (direction in ('LONG', 'SHORT')),
  horizon_minutes integer not null,
  claimed_at timestamptz not null,
  extractor text not null,
  excerpt text not null default '',
  created_at timestamptz not null default now(),
  unique (quarantine_id, symbol)
);

create index if not exists idx_evidence_claims_source on evidence_claims(source_id, claimed_at desc);
create index if not exists idx_evidence_claims_symbol on evidence_claims(symbol, claimed_at desc);

create table if not exists evidence_claim_outcomes (
  id uuid primary key default gen_random_uuid(),
  claim_id uuid not null references evidence_claims(id) on delete cascade,
  symbol text not null,
  direction text not null,
  horizon_minutes integer not null,
  status text not null,
  entry_price double precision,
  exit_price double precision,
  forward_return_pct double precision,
  signed_return_pct double precision,
  candles_used integer not null default 0,
  reason text not null default '',
  claimed_at timestamptz not null,
  measured_at timestamptz not null default now(),
  unique (claim_id, horizon_minutes)
);

create index if not exists idx_claim_outcomes_status on evidence_claim_outcomes(status, claimed_at);

-- DOWN
drop table if exists evidence_claim_outcomes;
drop table if exists evidence_claims;
drop table if exists quarantine_extractions;
