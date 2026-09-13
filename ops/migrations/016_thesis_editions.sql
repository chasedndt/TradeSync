-- UP
-- Daily thesis editions: the thesis for every tracked symbol, frozen at a
-- scheduled moment, with the text and the spoken script derived from it.
--
-- The live thesis page recomputes on every read. An edition is the record:
-- what the evidence said at the NY premarket, midday and session-handoff
-- checks (the same three editions the StrikeZone fleet publishes), kept so a
-- later reader, a narration, or a video renders the same thing the operator
-- saw. Media produced from an edition (audio, video) is attached under
-- ``media`` by the renderer, never generated inline here.

create table if not exists thesis_editions (
  id uuid primary key default gen_random_uuid(),
  edition text not null,
  generated_at timestamptz not null default now(),
  symbols jsonb not null default '[]'::jsonb,
  theses jsonb not null default '{}'::jsonb,
  headline text not null default '',
  text text not null default '',
  narration text not null default '',
  verdicts jsonb not null default '{}'::jsonb,
  media jsonb not null default '{}'::jsonb,
  schema_version text not null default 'thesis_edition_v1',
  trigger text not null default 'schedule'
);

create index if not exists idx_thesis_editions_recent on thesis_editions(generated_at desc);

-- DOWN
drop table if exists thesis_editions;
