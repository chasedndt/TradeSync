-- UP
CREATE TABLE managed_paper_control (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 entries_paused boolean NOT NULL DEFAULT true,
 reason text NOT NULL DEFAULT 'Initial paper safety review required',
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
INSERT INTO managed_paper_control(singleton) VALUES(true);
CREATE TABLE managed_paper_control_events (
 id uuid PRIMARY KEY,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 entries_paused boolean NOT NULL,
 reason text NOT NULL
);
-- DOWN
DROP TABLE managed_paper_control_events;
DROP TABLE managed_paper_control;
