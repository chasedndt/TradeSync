-- UP
-- The regime a paper opportunity fired into, known at entry.
--
-- The first regime split labelled each hour from the average forward return
-- of that hour's own outcomes — the returns then being scored. Nobody could
-- have known that label when the signal fired. This table stores a label
-- computed only from candles that had fully closed before the opportunity's
-- timestamp (tradesync_core.entry_regime), once per opportunity, with the
-- evidence that produced it, so a skill measurement can group by something the
-- operator could actually have observed.
--
-- "unknown" is a real value: a gap in venue history before entry yields no
-- label rather than a guessed one.

create table if not exists opportunity_entry_regimes (
  opportunity_id uuid primary key references opportunities(id) on delete cascade,
  symbol text not null,
  regime text not null check (regime in ('rising', 'falling', 'flat', 'unknown')),
  trailing_return_pct double precision,
  lookback_minutes integer not null,
  candles_used integer not null default 0,
  candle_interval text not null default '1m',
  window_start_s bigint,
  window_end_s bigint,
  reason text not null default '',
  schema_version text not null default 'entry_regime_v1',
  computed_at timestamptz not null default now()
);

create index if not exists idx_entry_regimes_symbol on opportunity_entry_regimes(symbol, regime);

-- DOWN
drop table if exists opportunity_entry_regimes;
