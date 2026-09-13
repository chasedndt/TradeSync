# The fleet in the dashboard, daily editions with narration, and the vault re-point

Date: 2026-09-13
Scope: migrations `016_thesis_editions.sql`, `017_fleet.sql`;
`libs/tradesync_core/tradesync_core/thesis_edition.py`;
`services/state-api/app/{editions,fleet}.py`; intake list gains extraction results;
`tools/{hermes_fleet_bridge,repoint_hermes_vault,thesis_video}.py`;
Cockpit `Fleet` page, `EditionPanel` on the Thesis page, `KnowledgeIntake` rewritten;
scheduled tasks `TradeSync-Hermes-Fleet-Bridge` (5 min) and `TradeSync-Thesis-Edition-Renderer` (10 min).

The operator's instructions of 2026-09-13: re-point the fleet to the canonical
vault; put the daily thesis edition in its own panel and route everything
to it; reuse the TTS and content workflow ChaseOS already defines for the
video; make the Knowledge Intake readable; show every cron job with its
description in a panel where its frequency can be changed; lower the
five-minute jobs for now so compute can be estimated, with analytics.

## 1. Fleet re-pointed to `chaseos_chaseintech`

Audited first (read-only): 40 job records (38 by working directory, 2 by
prompt), 119 scripts with 184 lines, the terminal `cwd` in `config.yaml`,
five lines across the two Windows launchers, and `repo_root` in the Discord
bindings file all named the retired stub. The canonical vault already holds
every directory the fleet writes to; its Windows interpreter is
`.venv-win314` (the `.venv` there is a POSIX venv), so the launcher line that
hardcoded `.venv\Scripts\python.exe` was pointed at `.venv-win314`.

`tools/repoint_hermes_vault.py` took a full backup
(`dashboard-runtime\backups\repoint-20260913_043749`) and applied every
replacement, both spellings. A second dry run finds nothing left. Hermes
re-reads its registry on every tick, so the working-directory change was
live within a minute without a restart. Nothing was deleted from the old
vault; its `07_LOGS` content is still there.

## 2. The Fleet page

The host bridge posts the fleet's registry, execution ledger and token
usage audit to `POST /state/fleet/snapshot` every five minutes (85 jobs,
~1,000 runs, 266 model-call audit rows on the first pass). The page shows
every job with its description (the prompt's first sentences, or the script
it runs), cadence, mode, delivery, last result, runs in 24 hours, tokens in
24 hours and 7 days, and a schedule selector plus enable/disable. Those send
**directives**: a request that stays pending until the bridge applies it to
`jobs.json`, with a timestamped backup and an atomic write, and reports the
value it replaced. A schedule change makes Hermes re-anchor the job's next
run; nothing else in the record is touched.

**Frequencies lowered.** Every enabled job at a cadence of 15 minutes or
faster (15 jobs, from every minute to every 15) was set to every 30 minutes
by directive, requested as "operator (compute budget 2026-09-13)". All 15
were applied on the bridge's next pass, previous values kept, reversible
from the panel.

**Analytics.** Token usage per day and per job comes from the fleet's own
`usage_audit.jsonl`: prompt and completion tokens, model, duration, per
fire. Script jobs use no tokens. No price is assumed; the panel says so.
The first audit rows show single agent runs consuming 250k to 740k prompt
tokens, which is where the compute goes, not the five-minute scripts.

## 3. Daily editions, narrated

`GET/POST /state/thesis/editions` freezes the thesis for every tracked
symbol at the StrikeZone cadence in London time (NY premarket 12:00, NY
midday 17:30, session handoff 23:30) or on request, composing a headline,
the written edition and a spoken script from the thesis lines alone. A
manual edition of ten symbols took 131 seconds. The Thesis page shows the
latest edition first, with the written and spoken renderings and a
generate-now control.

**Narration and video** use exactly what ChaseOS already uses: the fleet's
configured TTS provider is Microsoft Edge neural TTS (`edge-tts`, voice
`en-US-AriaNeural`), its one working video pipeline is Pillow slides plus
edge-tts plus ffmpeg (`scripts/generate_year2_term1_videos.py`), and ffmpeg
is on the Windows PATH. `tools/thesis_video.py` applies those primitives to
an edition: one slide per symbol, narration per slide, segments encoded and
concatenated, an SRT muxed in, written under `dashboard-runtime\editions\<id>\`
and attached to the edition by filename. State-api serves the files
read-only by bare name. The renderer runs every ten minutes and picks up
any edition without media.

## 4. Knowledge Intake, readable

Each held item is rendered by its schema: a Pine alert shows indicator,
ticker, interval, action and note; a Discord post shows channel, author
and text with embeds; a Hermes run shows the job, cadence and delivery; a
harness answer shows the intent and the answer. Every item carries what
extraction made of it (rule pass, harness pass, claims or the reason for
none), there are source tabs, a text filter and a tally, and the raw JSON
sits behind a disclosure.

## Tests

Root: `test_thesis_edition.py`. Existing suites unchanged. The bridge and
renderer are host scripts exercised live (snapshot posted, 15 directives
applied, edition generated).
