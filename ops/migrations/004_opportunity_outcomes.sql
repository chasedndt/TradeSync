-- UP
-- Measured market movement after a recorded paper opportunity.
--
-- These rows are observations of what the market did, not records of trades.
-- No order was placed and no position existed. Storing them is what turns a
-- stream of opinions into a track record that can be argued with.

create table if not exists opportunity_outcomes (
  id uuid primary key default gen_random_uuid(),
  opportunity_id uuid not null references opportunities(id) on delete cascade,
  symbol text not null,
  direction text not null check (direction in ('LONG', 'SHORT')),
  horizon_minutes integer not null check (horizon_minutes > 0),
  status text not null check (status in ('measured', 'pending', 'insufficient_candles')),

  -- Populated only when status = 'measured'.
  entry_price double precision,
  exit_price double precision,
  forward_return_pct double precision,
  -- forward_return_pct signed by the side that was called, so a SHORT that
  -- fell reads positive. This is the "was the call right" column.
  signed_return_pct double precision,
  max_favourable_pct double precision,
  max_adverse_pct double precision,
  candles_used integer not null default 0,
  reason text not null default '',

  opened_at timestamptz not null,
  measured_at timestamptz not null default now(),

  -- One verdict per opportunity per horizon; re-measuring updates in place.
  unique (opportunity_id, horizon_minutes)
);

create index if not exists idx_outcomes_symbol_horizon
  on opportunity_outcomes(symbol, horizon_minutes, opened_at desc);

create index if not exists idx_outcomes_status
  on opportunity_outcomes(status, horizon_minutes);

-- DOWN
drop table if exists opportunity_outcomes;
