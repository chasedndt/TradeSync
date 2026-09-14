-- UP
CREATE TABLE research_trials (
 id uuid PRIMARY KEY,
 registered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 specification jsonb NOT NULL,
 specification_sha256 text NOT NULL UNIQUE CHECK(length(specification_sha256)=64)
);
CREATE FUNCTION protect_research_trial() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 RAISE EXCEPTION 'Research trial registration is immutable; register a new specification';
END $$;
CREATE TRIGGER research_trial_immutable BEFORE UPDATE OR DELETE ON research_trials
 FOR EACH ROW EXECUTE FUNCTION protect_research_trial();
-- DOWN
DROP TABLE research_trials;
DROP FUNCTION protect_research_trial();
