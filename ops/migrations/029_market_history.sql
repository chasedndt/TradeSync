-- UP
-- Durable market history for the liquidity heatmap, the estimated liquidation
-- map and the timeframe records. Redis keeps only a bounded hot window, so
-- anything a higher-timeframe view needs is recorded here once a minute:
-- aggregated Hyperliquid order books, Hyperliquid open interest, and
-- liquidations received from other venues (context only, never authority).
-- Retention downsamples order books to 15 minutes after 3 days and open
-- interest to 15 minutes after 7 days (see tradesync_core.market_history).

create table if not exists market_depth_snapshots (
  symbol text not null,
  n_sig_figs smallint not null check (n_sig_figs between 2 and 5),
  observed_at timestamptz not null,
  mid_price double precision,
  bids jsonb not null,
  asks jsonb not null,
  recorded_at timestamptz not null default now(),
  primary key (symbol, n_sig_figs, observed_at)
);

create table if not exists market_open_interest (
  symbol text not null,
  observed_at timestamptz not null,
  open_interest_usd double precision not null check (open_interest_usd >= 0),
  mark_price double precision not null check (mark_price > 0),
  oracle_price double precision,
  funding_rate double precision,
  oracle_premium_bps double precision,
  volume_24h_usd double precision,
  recorded_at timestamptz not null default now(),
  primary key (symbol, observed_at)
);

create table if not exists market_liquidation_events (
  source text not null check (source in ('bybit', 'binance', 'okx')),
  event_id text not null,
  symbol text not null,
  event_time timestamptz not null,
  position_side text not null check (position_side in ('long', 'short')),
  price double precision not null check (price > 0),
  size double precision not null check (size > 0),
  notional_usd double precision not null check (notional_usd > 0),
  price_kind text not null check (price_kind in ('bankruptcy', 'average_fill')),
  received_at timestamptz not null,
  primary key (source, event_id)
);

create index if not exists idx_market_liquidations_symbol_time
  on market_liquidation_events (symbol, event_time desc);

-- DOWN
drop table if exists market_liquidation_events;
drop table if exists market_open_interest;
drop table if exists market_depth_snapshots;
