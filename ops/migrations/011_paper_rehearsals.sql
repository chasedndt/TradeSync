-- UP
-- The paper rehearsal journal.
--
-- A rehearsal is a simulated fill for an opportunity: the risk rules applied,
-- the plan, the mark and spread it was priced from, the fee schedule used, and
-- the resulting entry cost. It exists so the operator can exercise the whole
-- decision path — preview, refuse, journal — while EXECUTION_ENABLED stays
-- false. Nothing in this table is an order, and nothing reads it to place one.
--
-- One rehearsal per opportunity: the unique constraint is how a duplicate
-- submission returns the existing row instead of a second simulated fill.

create table if not exists paper_rehearsals (
  id uuid primary key default gen_random_uuid(),
  opportunity_id uuid not null unique references opportunities(id) on delete cascade,
  symbol text not null,
  direction text not null check (direction in ('LONG', 'SHORT')),
  size_usd double precision not null check (size_usd > 0),
  -- rehearsed: a simulated fill was produced. refused: a risk rule said no,
  -- or the market data needed to price a fill was not available.
  status text not null check (status in ('rehearsed', 'refused')),
  plan jsonb not null,
  risk_verdict jsonb not null,
  fill jsonb,
  market jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  note text not null default 'Simulated. No order was placed; no wallet or signer exists.'
);

create index if not exists idx_paper_rehearsals_created on paper_rehearsals(created_at desc);
create index if not exists idx_paper_rehearsals_symbol on paper_rehearsals(symbol, created_at desc);

-- DOWN
drop table if exists paper_rehearsals;
