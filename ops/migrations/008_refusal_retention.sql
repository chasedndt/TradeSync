-- UP
-- Permanent aggregate of refused paper verdicts.
--
-- Every scoring pass records one verdict per symbol, admitted or refused. The
-- refusals are the reason the dashboard can say why no opportunity exists, and
-- they are also about 4,300 rows of evidence JSON a day, kept forever.
--
-- Deleting them outright is not an option. Refusals are the **denominator**:
-- "the coverage floor blocked 61% of ETH verdicts last Tuesday" is unanswerable
-- once they are gone, and every admission statistic computed afterwards would
-- silently improve. For a system whose claim is that it does not flatter
-- itself, that is the worst available failure.
--
-- So a refusal is rolled up before it is removed. This table is the permanent
-- record; the full rows in `signals` are kept for a recent window, where they
-- are actually read. Retention never touches this table.

create table if not exists signal_refusal_daily (
  -- UTC calendar day of the refusals being summarised.
  day date not null,
  symbol text not null,
  -- The primary reason: the first gate the evidence failed. A verdict can fail
  -- several at once, but it is filed under exactly one, because counting it
  -- under each would make the refusal totals sum to more than the number of
  -- refusals and an exact denominator is the only reason this table exists.
  -- 'unstated' for a row that carried no reason at all; it is still counted,
  -- since dropping it would understate the denominator just as badly.
  reason text not null,
  -- Every code seen in this bucket, primary or not, as {code: count}. These
  -- counts may exceed `refusals`; that one stays exact.
  reason_codes jsonb not null default '{}'::jsonb,

  refusals integer not null check (refusals >= 0),
  -- How many of those rows actually carried each measure. Two counts, not
  -- one: a refusal can carry a coverage without a score, and weighting the
  -- coverage mean by the score count would discard it. Means are recombined
  -- weighted by these, so a small later batch cannot drag a large day's
  -- average toward itself.
  scored_rows integer not null default 0 check (scored_rows >= 0),
  covered_rows integer not null default 0 check (covered_rows >= 0),

  -- Null rather than zero when nothing carried the field: a mean of zero is a
  -- claim about the scores, and an absent field is not.
  mean_score double precision,
  mean_coverage double precision,
  min_coverage double precision,
  max_coverage double precision,

  first_rolled_at timestamptz not null default now(),
  last_rolled_at timestamptz not null default now(),

  primary key (day, symbol, reason)
);

create index if not exists idx_signal_refusal_daily_day
  on signal_refusal_daily (day desc);
create index if not exists idx_signal_refusal_daily_reason
  on signal_refusal_daily (reason, day desc);

-- Retention only ever deletes refusals, and only after they are rolled up.
-- This index makes that sweep cheap; without it the pass scans the whole table
-- every five minutes.
create index if not exists idx_signals_kind_created
  on signals (kind, created_at);

-- DOWN
drop index if exists idx_signals_kind_created;
drop index if exists idx_signal_refusal_daily_reason;
drop index if exists idx_signal_refusal_daily_day;
drop table if exists signal_refusal_daily;
