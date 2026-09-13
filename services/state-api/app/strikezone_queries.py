"""SQL for the StrikeZone quant lab routes. Every ledger query is scoped to one methodology ($1)."""

LATEST_SQL = """
SELECT DISTINCT ON (asset, timeframe) asset, timeframe, direction, confidence, signal_at
FROM sz_signals WHERE methodology_version = $1
ORDER BY asset, timeframe, signal_at DESC
"""

LATEST_TRADES_SQL = """
SELECT DISTINCT ON (s.asset, s.timeframe) s.asset, s.timeframe, s.direction, s.signal_at, s.expiry_at,
       s.entry_price, s.invalidation_price, s.target_price,
       EXISTS (SELECT 1 FROM sz_outcomes o WHERE o.signal_id = s.signal_id) AS has_outcome
FROM sz_signals s WHERE s.methodology_version = $1 AND s.direction <> 'no_trade'
ORDER BY s.asset, s.timeframe, s.signal_at DESC
"""

COUNTS_SQL = """
SELECT asset, timeframe,
       count(*) FILTER (WHERE signal_at > now() - interval '24 hours') AS calls_24h,
       count(*) FILTER (WHERE signal_at > now() - interval '24 hours' AND direction <> 'no_trade') AS trades_24h
FROM sz_signals WHERE methodology_version = $1 GROUP BY asset, timeframe
"""

RESULTS_SQL = """
SELECT asset, timeframe, count(*) AS resolved, count(*) FILTER (WHERE net_pnl_usdc > 0) AS wins,
       coalesce(sum(net_pnl_usdc), 0) AS net
FROM sz_outcomes WHERE methodology_version = $1 AND exit_at > now() - interval '7 days'
GROUP BY asset, timeframe
"""

PENDING_SQL = """
SELECT s.asset, s.timeframe, s.expiry_at FROM sz_signals s
WHERE s.methodology_version = $1 AND s.direction <> 'no_trade' AND s.signal_at > now() - interval '3 days'
  AND NOT EXISTS (SELECT 1 FROM sz_outcomes o WHERE o.signal_id = s.signal_id)
"""

CURVE_SQL = """
SELECT exit_at, net_pnl_usdc FROM sz_outcomes
WHERE methodology_version = $1 AND exit_at IS NOT NULL AND net_pnl_usdc IS NOT NULL
ORDER BY exit_at
"""

TOTALS_SQL = """
SELECT (SELECT count(*) FROM sz_signals WHERE methodology_version = $1) AS signals,
       (SELECT count(*) FROM sz_signals WHERE methodology_version = $1 AND direction <> 'no_trade') AS trades,
       (SELECT count(*) FROM sz_outcomes WHERE methodology_version = $1) AS outcomes,
       (SELECT max(signal_at) FROM sz_signals WHERE methodology_version = $1) AS last_signal_at,
       (SELECT max(exit_at) FROM sz_outcomes WHERE methodology_version = $1) AS last_outcome_at
"""

LEDGER_SQL = """
SELECT s.signal_id, s.asset, s.timeframe, s.direction, s.signal_at, s.expiry_at, s.confidence,
       s.entry_price, s.invalidation_price, s.target_price, s.regime,
       o.outcome_id, o.exit_reason, o.exit_at, o.holding_minutes, o.net_pnl_usdc, o.gross_pnl_usdc,
       o.fees_usdc, o.slippage_usdc, o.funding_usdc, o.entry_fill_price, o.exit_fill_price
FROM sz_signals s
LEFT JOIN LATERAL (
  SELECT * FROM sz_outcomes x WHERE x.signal_id = s.signal_id ORDER BY x.exit_at DESC NULLS LAST LIMIT 1
) o ON true
WHERE s.methodology_version = $1
  AND ($2::text IS NULL OR s.asset = $2)
  AND ($3::text IS NULL OR s.timeframe = $3)
  AND CASE $4::text
        WHEN 'trades' THEN s.direction <> 'no_trade'
        WHEN 'open' THEN s.direction <> 'no_trade' AND o.outcome_id IS NULL
        WHEN 'resolved' THEN o.outcome_id IS NOT NULL
        WHEN 'no_trade' THEN s.direction = 'no_trade'
        ELSE true
      END
ORDER BY s.signal_at DESC
LIMIT $5
"""

# The lab's own jobs (quant_eval scripts), the StrikeZone health watchdogs, and the fleet-wide inspector.
LAB_JOBS_SQL = """
SELECT j.job_id, j.name, j.enabled, j.schedule_display, j.last_status, j.last_run_at, j.next_run_at,
       j.last_error, j.last_delivery_error,
       coalesce(r.runs_24h, 0) AS runs_24h, coalesce(r.failed_24h, 0) AS failed_24h
FROM fleet_jobs j
LEFT JOIN (
  SELECT job_id, count(*) FILTER (WHERE claimed_at > now() - interval '24 hours') AS runs_24h,
         count(*) FILTER (WHERE status = 'failed' AND claimed_at > now() - interval '24 hours') AS failed_24h
  FROM fleet_runs GROUP BY job_id
) r USING (job_id)
WHERE j.script ILIKE '%quant_eval%'
   OR (j.name ILIKE '%strikezone%' AND j.name ILIKE '%health%')
   OR j.name ILIKE '%cron-fleet health%'
ORDER BY (j.last_status = 'error') DESC, j.name
"""

FRESHNESS_SQL = """
SELECT (SELECT max(signal_at) FROM sz_signals) AS last_signal_at,
       (SELECT greatest((SELECT max(ingested_at) FROM sz_signals), (SELECT max(ingested_at) FROM sz_outcomes))) AS last_ingest_at,
       (SELECT max(snapshot_at) FROM sz_documents) AS last_document_at
"""
