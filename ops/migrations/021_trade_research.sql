-- UP
-- Append-only research snapshots; never an execution or strategy-promotion table.
CREATE TABLE IF NOT EXISTS trade_research_runs (
    id uuid PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    symbol text NOT NULL,
    style text NOT NULL CHECK (style IN ('scalp', 'swing')),
    version text NOT NULL,
    input_sha256 text NOT NULL,
    candles jsonb NOT NULL,
    result jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS trade_research_runs_created ON trade_research_runs(created_at DESC);
-- DOWN
DROP TABLE IF EXISTS trade_research_runs;
