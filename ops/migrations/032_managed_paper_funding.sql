-- UP
-- Settled funding evidence for managed paper positions (tradesync_core.paper_funding).
-- One row per position per hourly Hyperliquid settlement it took part in: the
-- published rate, the price the settlement was valued at, where that price came
-- from, and the payment (positive when the position paid). Rows are append-only:
-- an update or delete is refused, so the funding behind a position's net cannot
-- be rewritten after the fact. Creates no rows by itself.

CREATE TABLE IF NOT EXISTS managed_paper_funding (
 position_id uuid NOT NULL REFERENCES managed_paper_positions(id),
 settled_at timestamptz NOT NULL CHECK (extract(epoch FROM settled_at)::bigint % 3600 = 0),
 funding_rate double precision NOT NULL,
 premium double precision,
 side text NOT NULL CHECK (side IN ('long', 'short')),
 quantity double precision NOT NULL CHECK (quantity > 0),
 price double precision NOT NULL CHECK (price > 0),
 price_source text NOT NULL,
 price_observed_at timestamptz,
 payment_usdc double precision NOT NULL,
 source text NOT NULL DEFAULT 'hyperliquid_funding_history',
 received_at timestamptz NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY (position_id, settled_at)
);
CREATE OR REPLACE FUNCTION protect_managed_paper_funding() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 RAISE EXCEPTION 'Managed paper funding settlements are append-only';
END $$;
DROP TRIGGER IF EXISTS managed_paper_funding_append_only ON managed_paper_funding;
CREATE TRIGGER managed_paper_funding_append_only BEFORE UPDATE OR DELETE ON managed_paper_funding
 FOR EACH ROW EXECUTE FUNCTION protect_managed_paper_funding();
-- DOWN
DROP TABLE IF EXISTS managed_paper_funding;
DROP FUNCTION IF EXISTS protect_managed_paper_funding();
