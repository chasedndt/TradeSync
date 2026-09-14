-- UP
-- Outcome attribution and weight-learning proposals for paper opportunities.
--
-- opportunity_attributions: one row per opportunity per measured horizon. It
-- states what the call earned after an explicit round-trip cost, names the
-- result (clean_win, win_after_drawdown, wrong_direction, reversed,
-- no_follow_through), explains it in one sentence, and records every feature
-- and block of the stored decision as supported, misled or neutral
-- (tradesync_core.attribution). Rows are derived: the learning job rewrites a
-- row when its outcome is re-measured, its entry regime arrives, or the cost
-- or schema changes, so the table can always be rebuilt from the outcomes.
--
-- learning_proposals: challenger rulebooks learned from older attributions and
-- tested by walk-forward replay on newer decisions. A proposal is evidence for
-- an operator decision, never an activation. Adoption writes the rulebook to
-- regime_rulebooks and a row to regime_weight_activations (migration 002); the
-- proposal records who decided, when, and the activation it created. At most
-- one proposal per rulebook is open at a time; a newer one supersedes it.

create table if not exists opportunity_attributions (
  opportunity_id uuid not null references opportunities(id) on delete cascade,
  horizon_minutes integer not null check (horizon_minutes > 0),
  symbol text not null,
  direction text not null check (direction in ('LONG', 'SHORT')),
  opened_at timestamptz not null,
  classification text not null check (classification in (
    'clean_win', 'win_after_drawdown', 'wrong_direction', 'reversed', 'no_follow_through'
  )),
  reason text not null,
  signed_return_pct double precision not null,
  net_return_pct double precision not null,
  cost_pct double precision not null check (cost_pct >= 0),
  max_favourable_pct double precision,
  max_adverse_pct double precision,
  entry_regime text not null default 'unknown'
    check (entry_regime in ('rising', 'falling', 'flat', 'unknown')),
  features jsonb not null default '[]'::jsonb,
  blocks jsonb not null default '[]'::jsonb,
  rulebook_version text,
  rulebook_digest text,
  outcome_measured_at timestamptz not null,
  schema_version text not null,
  attributed_at timestamptz not null default now(),
  primary key (opportunity_id, horizon_minutes)
);

create index if not exists idx_attributions_horizon_opened
  on opportunity_attributions(horizon_minutes, opened_at desc);

create index if not exists idx_attributions_classification
  on opportunity_attributions(classification, opened_at desc);

create table if not exists learning_proposals (
  id uuid primary key default gen_random_uuid(),
  status text not null default 'proposed'
    check (status in ('proposed', 'adopted', 'rejected', 'superseded')),
  rulebook_id text not null,
  rulebook_horizon text not null,
  target_horizon_minutes integer not null check (target_horizon_minutes > 0),
  parent_version text not null,
  parent_digest text not null,
  version text not null,
  config_digest text not null,
  config jsonb not null,
  hypothesis text not null,
  weights jsonb not null,
  evidence jsonb not null,
  replay jsonb not null,
  cost_pct double precision not null check (cost_pct >= 0),
  created_by text not null default 'learning-job',
  created_at timestamptz not null default now(),
  decided_at timestamptz,
  decided_by text,
  decision_note text not null default '',
  activation_id uuid references regime_weight_activations(id),
  reverted_at timestamptz,
  reverted_by text,
  check (status = 'proposed' or (decided_at is not null and decided_by is not null)),
  check (activation_id is null or status = 'adopted'),
  check (reverted_at is null or status = 'adopted')
);

create unique index if not exists uq_learning_proposals_open
  on learning_proposals(rulebook_id) where status = 'proposed';

create index if not exists idx_learning_proposals_created
  on learning_proposals(created_at desc);

-- DOWN
drop index if exists idx_learning_proposals_created;
drop index if exists uq_learning_proposals_open;
drop table if exists learning_proposals;
drop index if exists idx_attributions_classification;
drop index if exists idx_attributions_horizon_opened;
drop table if exists opportunity_attributions;
