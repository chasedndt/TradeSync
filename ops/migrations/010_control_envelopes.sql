-- UP
-- ChaseOS approvals bound to paper candidates, recorded so each is used once.
--
-- A control envelope binds one authenticated ChaseOS decision to one immutable
-- candidate. `control_envelope.py` already enforces the shape: paper_only mode,
-- the closed authority ceiling, a candidate that must stay review_only, and an
-- approval whose scope is "once".
--
-- "Once" is the part a library cannot enforce on its own. Single use is a fact
-- about history, not about a document, so it lives here: `approval_id` is
-- unique, and a replay of the same approval hits that constraint rather than
-- authorising a second evaluation.
--
-- What an envelope authorises is one **paper evaluation**. It is never an
-- exchange order, a wallet, a credential, a signature, or a live dispatch —
-- CLOSED_AUTHORITY says so on every envelope, and this table stores that
-- verbatim so an audit reads the ceiling that actually applied rather than the
-- one the code has today.

create table if not exists control_envelopes (
  envelope_id text primary key,

  -- Unique: this is the single-use enforcement. A replayed approval collides
  -- here instead of authorising a second evaluation.
  approval_id text not null unique,
  approval_decision_id text not null,
  approval_digest text not null,
  approved_at timestamptz not null,

  candidate_id text not null,
  -- Integrity: the envelope carries a hash of the candidate it was built for.
  -- Stored so a later read can prove the candidate was not swapped after
  -- approval.
  candidate_hash text not null,
  candidate jsonb not null,

  -- The authority ceiling as it stood when this was approved, verbatim.
  authority jsonb not null,

  -- Which quarantined item the candidate was extracted from, so an evaluation
  -- traces back to the alert that produced it.
  source_quarantine_id uuid,

  created_at timestamptz not null default now(),
  -- Set when a paper evaluation actually consumes it. An envelope that exists
  -- but was never consumed is a recorded approval nobody acted on, which is a
  -- different thing from one that was used.
  consumed_at timestamptz,
  consumed_by text
);

create index if not exists idx_control_envelopes_candidate
  on control_envelopes (candidate_id);
create index if not exists idx_control_envelopes_unconsumed
  on control_envelopes (created_at desc) where consumed_at is null;

-- DOWN
drop index if exists idx_control_envelopes_unconsumed;
drop index if exists idx_control_envelopes_candidate;
drop table if exists control_envelopes;
