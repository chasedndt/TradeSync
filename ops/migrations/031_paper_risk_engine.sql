-- UP
-- Paper risk engine: account ledger, operator limits, kill switch, restart
-- reconciliation and measured correlation. Paper only; nothing here grants
-- execution authority. Seeds conservative limits and a disengaged kill switch.

-- Pause changes record who made them. The earlier route did not send a name.
ALTER TABLE managed_paper_control_events ADD COLUMN operator text NOT NULL DEFAULT 'unrecorded';

CREATE FUNCTION paper_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END $$;

CREATE TABLE paper_account (
 singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
 starting_capital_usdc numeric NOT NULL CHECK (starting_capital_usdc > 0),
 cash_usdc numeric NOT NULL,
 realised_pnl_usdc numeric NOT NULL DEFAULT 0,
 gross_pnl_usdc numeric NOT NULL DEFAULT 0,
 fees_usdc numeric NOT NULL DEFAULT 0,
 funding_usdc numeric NOT NULL DEFAULT 0,
 slippage_usdc numeric NOT NULL DEFAULT 0,
 closed_positions integer NOT NULL DEFAULT 0 CHECK (closed_positions >= 0),
 last_sequence bigint NOT NULL,
 peak_equity_usdc numeric NOT NULL,
 peak_equity_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE paper_account_ledger (
 sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 id uuid NOT NULL UNIQUE,
 kind text NOT NULL CHECK (kind IN ('capital', 'realised', 'funding_adjustment')),
 position_id uuid REFERENCES managed_paper_positions(id),
 occurred_at timestamptz NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 amount_usdc numeric NOT NULL,
 gross_pnl_usdc numeric NOT NULL DEFAULT 0,
 fees_usdc numeric NOT NULL DEFAULT 0,
 funding_usdc numeric NOT NULL DEFAULT 0,
 slippage_usdc numeric NOT NULL DEFAULT 0,
 balance_after_usdc numeric NOT NULL,
 detail jsonb NOT NULL DEFAULT '{}'::jsonb,
 CHECK ((kind = 'capital') = (position_id IS NULL)),
 CHECK (kind = 'capital' OR amount_usdc = gross_pnl_usdc - fees_usdc - funding_usdc),
 CHECK (kind <> 'funding_adjustment' OR (gross_pnl_usdc = 0 AND fees_usdc = 0 AND slippage_usdc = 0 AND funding_usdc <> 0))
);
CREATE UNIQUE INDEX paper_account_ledger_one_capital ON paper_account_ledger (kind) WHERE kind = 'capital';
-- One realised entry per position; funding settled after its close arrives as adjustments.
CREATE UNIQUE INDEX paper_account_ledger_one_realised ON paper_account_ledger (position_id) WHERE kind = 'realised';
CREATE INDEX paper_account_ledger_position ON paper_account_ledger (position_id);
CREATE INDEX paper_account_ledger_occurred ON paper_account_ledger (occurred_at);
CREATE TRIGGER paper_account_ledger_append_only BEFORE UPDATE OR DELETE ON paper_account_ledger
 FOR EACH ROW EXECUTE FUNCTION paper_append_only();
CREATE TRIGGER paper_account_ledger_no_truncate BEFORE TRUNCATE ON paper_account_ledger
 FOR EACH STATEMENT EXECUTE FUNCTION paper_append_only();

CREATE TABLE paper_equity_peaks (
 id uuid PRIMARY KEY,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 equity_usdc numeric NOT NULL,
 cash_usdc numeric NOT NULL,
 unrealised_usdc numeric NOT NULL,
 marks jsonb NOT NULL
);
CREATE TRIGGER paper_equity_peaks_append_only BEFORE UPDATE OR DELETE ON paper_equity_peaks
 FOR EACH ROW EXECUTE FUNCTION paper_append_only();

CREATE TABLE paper_risk_limits (
 singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
 daily_loss_limit_usdc double precision NOT NULL DEFAULT 200 CHECK (daily_loss_limit_usdc > 0),
 max_drawdown_fraction double precision NOT NULL DEFAULT 0.06 CHECK (max_drawdown_fraction > 0 AND max_drawdown_fraction < 1),
 max_gross_exposure_fraction double precision NOT NULL DEFAULT 0.35 CHECK (max_gross_exposure_fraction > 0 AND max_gross_exposure_fraction <= 10),
 max_symbol_exposure_fraction double precision NOT NULL DEFAULT 0.12 CHECK (max_symbol_exposure_fraction > 0),
 max_bucket_exposure_fraction double precision NOT NULL DEFAULT 0.25 CHECK (max_bucket_exposure_fraction > 0),
 correlation_threshold double precision NOT NULL DEFAULT 0.7 CHECK (correlation_threshold > 0 AND correlation_threshold <= 1),
 max_concurrent_positions integer NOT NULL DEFAULT 3 CHECK (max_concurrent_positions BETWEEN 1 AND 50),
 max_entry_quote_age_s double precision NOT NULL DEFAULT 15 CHECK (max_entry_quote_age_s > 0 AND max_entry_quote_age_s <= 30),
 max_mark_age_s double precision NOT NULL DEFAULT 60 CHECK (max_mark_age_s > 0 AND max_mark_age_s <= 600),
 operator text NOT NULL DEFAULT 'migration 031',
 reason text NOT NULL DEFAULT 'Initial conservative paper limits',
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK (max_symbol_exposure_fraction <= max_bucket_exposure_fraction),
 CHECK (max_bucket_exposure_fraction <= max_gross_exposure_fraction)
);
INSERT INTO paper_risk_limits (singleton) VALUES (true);

CREATE TABLE paper_risk_limit_events (
 id uuid PRIMARY KEY,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 operator text NOT NULL CHECK (length(btrim(operator)) > 0),
 reason text NOT NULL CHECK (length(btrim(reason)) >= 5),
 previous jsonb NOT NULL,
 updated jsonb NOT NULL
);
CREATE TRIGGER paper_risk_limit_events_append_only BEFORE UPDATE OR DELETE ON paper_risk_limit_events
 FOR EACH ROW EXECUTE FUNCTION paper_append_only();

CREATE TABLE paper_kill_switch (
 singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
 active boolean NOT NULL DEFAULT false,
 operator text NOT NULL DEFAULT 'migration 031',
 reason text NOT NULL DEFAULT 'Kill switch installed and not engaged',
 changed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
INSERT INTO paper_kill_switch (singleton) VALUES (true);

CREATE TABLE paper_kill_switch_events (
 id uuid PRIMARY KEY,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 action text NOT NULL CHECK (action IN ('kill', 'resume', 'close')),
 operator text NOT NULL CHECK (length(btrim(operator)) > 0),
 reason text NOT NULL CHECK (length(btrim(reason)) >= 5),
 position_id uuid REFERENCES managed_paper_positions(id),
 detail jsonb NOT NULL DEFAULT '{}'::jsonb,
 CHECK ((action = 'close') = (position_id IS NOT NULL))
);
CREATE TRIGGER paper_kill_switch_events_append_only BEFORE UPDATE OR DELETE ON paper_kill_switch_events
 FOR EACH ROW EXECUTE FUNCTION paper_append_only();

CREATE TABLE paper_reconciliation_runs (
 id uuid PRIMARY KEY,
 trigger text NOT NULL CHECK (trigger IN ('startup', 'periodic')),
 started_at timestamptz NOT NULL,
 finished_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 status text NOT NULL CHECK (status IN ('clean', 'mismatch', 'failed')),
 positions_checked integer NOT NULL DEFAULT 0,
 open_positions integer NOT NULL DEFAULT 0,
 mismatches jsonb NOT NULL DEFAULT '[]'::jsonb,
 gaps jsonb NOT NULL DEFAULT '[]'::jsonb,
 account jsonb NOT NULL DEFAULT '{}'::jsonb,
 error text
);
CREATE INDEX paper_reconciliation_runs_finished ON paper_reconciliation_runs (finished_at DESC);

CREATE TABLE paper_observation_gaps (
 id uuid PRIMARY KEY,
 position_id uuid NOT NULL REFERENCES managed_paper_positions(id),
 symbol text NOT NULL,
 started_at timestamptz NOT NULL,
 ended_at timestamptz,
 detected_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE (position_id, started_at),
 CHECK (ended_at IS NULL OR ended_at > started_at)
);

CREATE TABLE paper_correlation_measurements (
 id uuid PRIMARY KEY,
 measured_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 bar_interval text NOT NULL,
 window_bars integer NOT NULL CHECK (window_bars > 1),
 symbols jsonb NOT NULL,
 matrix jsonb NOT NULL,
 overlap_counts jsonb NOT NULL,
 unmeasured jsonb NOT NULL DEFAULT '[]'::jsonb,
 source text NOT NULL
);
CREATE INDEX paper_correlation_measurements_measured ON paper_correlation_measurements (measured_at DESC);
-- DOWN
DROP TABLE paper_correlation_measurements;
DROP TABLE paper_observation_gaps;
DROP TABLE paper_reconciliation_runs;
DROP TABLE paper_kill_switch_events;
DROP TABLE paper_kill_switch;
DROP TABLE paper_risk_limit_events;
DROP TABLE paper_risk_limits;
DROP TABLE paper_equity_peaks;
DROP TABLE paper_account_ledger;
DROP TABLE paper_account;
DROP FUNCTION paper_append_only();
ALTER TABLE managed_paper_control_events DROP COLUMN operator;
