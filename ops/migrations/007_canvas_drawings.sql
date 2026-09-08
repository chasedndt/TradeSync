-- UP
-- Operator drawings on the Market Canvas: levels, trendlines, ranges and notes.
--
-- Versioned rather than mutable. An edit inserts a new version and supersedes
-- the previous one, because "what did I think at the time" is a different
-- question from "what do I think now", and only the second survives an
-- overwrite. The roadmap requires a paper trade to be reconstructable from
-- source observation through outcome without screenshots or memory, and that
-- includes the operator's own reasoning at the time.
--
-- A drawing is annotation. It carries no scoring, approval or execution
-- authority and can never influence a signal.

create table if not exists canvas_drawings (
  id uuid primary key default gen_random_uuid(),
  -- Stable across versions: every version of one drawing shares this.
  drawing_id uuid not null,
  version integer not null check (version >= 1),

  symbol text not null,
  interval text not null,
  kind text not null check (kind in ('horizontal', 'trendline', 'range', 'note')),
  points jsonb not null,
  label text not null default '',
  colour text not null default '',

  created_by text not null default 'operator',
  created_at timestamptz not null default now(),
  -- Set when a later version or a delete supersedes this row. History is kept.
  superseded_at timestamptz,
  deleted boolean not null default false,

  unique (drawing_id, version)
);

-- The common read is "current drawings for this chart", which is every
-- drawing_id at its highest live version.
create index if not exists idx_canvas_current
  on canvas_drawings(symbol, interval, superseded_at)
  where superseded_at is null and deleted = false;

create index if not exists idx_canvas_history
  on canvas_drawings(drawing_id, version desc);

-- DOWN
drop table if exists canvas_drawings;
