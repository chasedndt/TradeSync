-- UP
-- Untrusted material from Tier B connectors, held for review.
--
-- Nothing here is evidence. Rows land in this table so an operator can see what
-- a connector sent before any of it can influence anything, and promotion to
-- admitted evidence is a separate, deliberate act.
--
-- Retention is bounded on purpose. An unbounded intake table is how the Redis
-- stream took the system down on 2026-09-07.

create table if not exists quarantine_intake (
  id uuid primary key default gen_random_uuid(),
  source text not null,
  accepted boolean not null,
  content_digest text not null,
  payload jsonb not null,
  reasons jsonb not null default '[]'::jsonb,

  observed_at timestamptz,
  received_at timestamptz not null default now(),

  -- Promotion is an operator act. These stay null until a human acts, and
  -- promoted_to records what the item became so the trail is inspectable.
  reviewed_by text,
  reviewed_at timestamptz,
  promoted_to text,

  -- Identical content from one source is a resubmission, not new evidence.
  unique (source, content_digest)
);

create index if not exists idx_quarantine_pending
  on quarantine_intake(received_at desc) where reviewed_at is null;

create index if not exists idx_quarantine_source
  on quarantine_intake(source, received_at desc);

-- DOWN
drop table if exists quarantine_intake;
