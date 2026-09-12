-- UP
-- Harness-proposed claim extraction, recorded once per quarantine row.
--
-- The rule extractor reads only what it can read: a tracked symbol and one
-- clear direction word in the same clause. Most agent prose is not written
-- that way. For those rows the advisory harness is asked what the post
-- *said*, in a shape that carries no authority (symbol, stance, horizon and
-- a verbatim quote), and every proposal is checked against the post's own
-- text before it becomes a claim. The resulting claim belongs to the post's
-- source, not to the harness; the harness is only the reader.
--
-- Recorded whether or not anything came of it, with the quarantine receipt
-- of the harness answer, so a row is asked about exactly once.

create table if not exists quarantine_harness_extractions (
  quarantine_id uuid primary key references quarantine_intake(id) on delete cascade,
  extractor text not null,
  claims integer not null default 0,
  reason text not null default '',
  receipt_digest text,
  extracted_at timestamptz not null default now()
);

-- DOWN
drop table if exists quarantine_harness_extractions;
