# TradeSync Database Migrations

This directory contains SQL migration files for managing schema changes in the TradeSync database.

## Migration File Naming Convention

Migration files follow this naming pattern:
```
<version>_<description>.sql
```

Examples:
- `001_initial_schema.sql`
- `002_add_agent_performance_table.sql`
- `003_add_index_to_events.sql`

Current repository migrations:

`031_paper_risk_engine.sql` adds the paper risk engine: an append-only account ledger with
stored balances and equity peaks, operator-editable limits with audit rows (seeded conservative),
a persistent kill switch (seeded disengaged) with audit rows, restart reconciliation runs,
observation gaps and measured correlation snapshots, and an `operator` column on pause audit rows.
Not yet applied; isolated, rolled-back UP/DOWN/UP acceptance is recorded in
[the change record](../../docs/changes/2026-09-15_paper-risk-engine.md).

`030_horizon_readings.sql` stores every Hermes reading of the timeframe outlook, one per band
(short term, lower, medium, higher), with its start and finish times and the measurement it read,
so the Timeframes page shows each reading's exact time, keeps the last good reading while a new one
runs, and flags a reading older than the numbers under it.

`029_market_history.sql` adds durable market history for the liquidity heatmap,
the estimated liquidation map and timeframe records: aggregated Hyperliquid order
books (nSigFigs 2 and 3), Hyperliquid open interest, and liquidations received from
Bybit and Binance (context only). Written once a minute by state-api's
`market_recorder`; retention downsamples to 15 minutes (books after 3 days, open
interest after 7) and drops books after 90 days and liquidations after 180. Applied
14 September as 031 and renumbered to 029 when the parallel branches merged; its UP
SQL only creates what does not exist, so recording it again as 029 changes nothing.

`027_canvas_drawing_kinds.sql` widens the canvas drawing kind check for the tool
rail (ray, extended_line, horizontal_ray, vertical, rectangle, fib_retracement,
pencil, text) and adds a nullable `style` jsonb per version. Not yet applied.
UP, DOWN and UP again verified on a throwaway PostgreSQL 17 cluster; DOWN keeps
rows of the newer kinds and restores the narrower check as NOT VALID.

`028_opportunity_learning.sql` adds per-horizon outcome attributions (result after
costs, classification, reason sentence, per-feature and per-block attribution) and
weight-learning proposals with walk-forward evidence and the operator's decision.
Adoption writes to the existing `regime_rulebooks` / `regime_weight_activations`
tables (002). Not yet applied.

`026_paper_control.sql` proposes default-paused persistent paper entry control and
an audit trail. Not yet applied; no current runtime control changed.

`025_research_trials.sql` proposes immutable research specifications and registration
timestamps. Applied locally 14 September after isolated SQL/API acceptance;
it creates no trial registrations automatically.

`024_mobile_preferences.sql` adds opt-in notification preferences and activation
timestamp. Applied locally 14 September after isolated UP/DOWN verification;
defaults enable no delivery.

`023_managed_paper_positions.sql` adds frozen managed-paper entry/plan storage,
separate lifecycle state/events and update protection. Creates no positions.

`022_mobile_alerts.sql` adds device enrollment and the durable notification outbox;
it creates no devices and enables no external sends by itself.

The numbered SQL files are the complete inventory; the older examples below
are not exhaustive. Latest: `021_trade_research.sql` stores paper research
candles, versioned assumptions and results separately from orders/approvals.
Applied locally on 13 September; see
[verification](../../docs/changes/2026-09-13_fleet-and-trade-research.md).

- `001_initial_schema.sql` — legacy initial operational schema.
- `002_regime_rulebooks.sql` — versioned paper rulebooks, activations, experiments, and replayable score events.
- `003_market_features.sql` — versioned feature catalogs, time-ordered observations, and replayable ordinary/robust normalization evidence.

`schema-init` runs the transactional migration runner after applying the
legacy-compatible base schema. Existing databases record and skip completed
versions; the runner never evaluates a migration's `-- DOWN` section.

**Version numbers** should be sequential integers padded with zeros (001, 002, 003, etc.).

## Migration File Structure

Each migration file contains two sections:

```sql
-- UP
-- SQL statements to apply the migration
CREATE TABLE ...;

-- DOWN
-- SQL statements to rollback the migration
DROP TABLE ...;
```

- **UP section**: Contains SQL to apply the migration (creating tables, adding columns, etc.)
- **DOWN section**: Contains SQL to rollback the migration (should reverse the UP changes)

## Creating a New Migration

Create the next zero-padded SQL file manually and include both `-- UP` and
`-- DOWN` boundaries. The bounded runner does not generate or roll back files.

## Running Migrations

### Apply all pending migrations:
```bash
python ops/migrate.py up
```

### Check migration status:
```bash
python ops/migrate.py status
```

## Migration Tracking

The migration tool automatically creates a `schema_migrations` table in your database to track which migrations have been applied:

```sql
CREATE TABLE schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  description TEXT NOT NULL
);
```

## Best Practices

1. **Always test migrations**: Test both UP and DOWN sections before committing
2. **Keep migrations small**: One logical change per migration file
3. **Make migrations reversible**: Always provide a proper DOWN section. The
   bounded runner supports `up` and `status`; rollback remains a manual,
   separately approved database operation.
4. **Use transactions**: Migrations are executed in transactions and rollback on failure
5. **Don't modify existing migrations**: Once applied to production, create a new migration instead

## Initial Setup

For a fresh database, run:
```bash
python ops/migrate.py up
```

This will apply all migrations starting from `001_initial_schema.sql`.
