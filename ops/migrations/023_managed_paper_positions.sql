-- UP
CREATE TABLE IF NOT EXISTS managed_paper_positions (
 id uuid PRIMARY KEY,
 opportunity_id uuid NOT NULL UNIQUE REFERENCES opportunities(id),
 symbol text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 entry_evidence jsonb NOT NULL,
 evidence_sha256 text NOT NULL,
 initial_plan jsonb NOT NULL,
 position_state jsonb NOT NULL,
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS managed_paper_events (
 id uuid PRIMARY KEY,
 position_id uuid NOT NULL REFERENCES managed_paper_positions(id),
 created_at timestamptz NOT NULL DEFAULT now(),
 kind text NOT NULL,
 payload jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS managed_paper_events_position ON managed_paper_events(position_id,created_at);
CREATE OR REPLACE FUNCTION protect_managed_paper_entry() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.entry_evidence IS DISTINCT FROM OLD.entry_evidence OR NEW.evidence_sha256 IS DISTINCT FROM OLD.evidence_sha256
 OR NEW.initial_plan IS DISTINCT FROM OLD.initial_plan OR NEW.opportunity_id IS DISTINCT FROM OLD.opportunity_id
 OR NEW.symbol IS DISTINCT FROM OLD.symbol OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
  RAISE EXCEPTION 'Managed paper entry evidence and plan are immutable';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER managed_paper_entry_immutable BEFORE UPDATE ON managed_paper_positions FOR EACH ROW EXECUTE FUNCTION protect_managed_paper_entry();
-- DOWN
DROP TABLE IF EXISTS managed_paper_events;
DROP TABLE IF EXISTS managed_paper_positions;
DROP FUNCTION IF EXISTS protect_managed_paper_entry();
