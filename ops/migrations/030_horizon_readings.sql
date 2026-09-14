-- UP
-- Hermes readings of the timeframe outlook, one per band (short term, lower,
-- medium, higher time frame), kept with the measurement they read. Every
-- attempt is a row: the page shows the exact time of the reading on screen,
-- keeps the last good reading visible while a new one runs or fails, and
-- flags a reading older than the numbers under it. Advisory text only; the
-- harness boundary files each answer in quarantine with a receipt.

create table if not exists horizon_readings (
  id uuid primary key default gen_random_uuid(),
  symbol text not null,
  scope text not null check (scope in ('short', 'lower', 'medium', 'higher')),
  status text not null check (status in ('running', 'ok', 'refused', 'unavailable', 'not_configured')),
  measured_at timestamptz not null,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  content text,
  model text,
  detail text,
  receipt jsonb
);

create index if not exists idx_horizon_readings_latest
  on horizon_readings (symbol, scope, started_at desc);

-- DOWN
drop table if exists horizon_readings;
