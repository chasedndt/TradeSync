# The ChaseOS fleet in Market Command: two bridges and the Agents page

Date: 2026-09-12
Scope: `libs/tradesync_core/tradesync_core/{discord_evidence,hermes_output}.py`,
`services/discord-reader/` (new service in `ops/compose.market-command.yml`),
`tools/hermes_output_bridge.py` (host bridge, Task Scheduler
`TradeSync-Hermes-Output-Bridge` every 2 min), `config/chaseos/discord-channels.json`,
`quarantine.KNOWN_SOURCES` gains `discord`,
`services/cockpit-ui/src/pages/{Agents,AgentsFeedItem}.tsx` at `/agents`,
`tools/set-runtime-secret.ps1`, `tools/copy-hermes-discord-token.ps1`, tests.

The operator's ChaseOS agents (the Hermes fleet: 85 cron jobs, 74 enabled)
and the Strike Zone alerts post to a private Discord server. The ask was to
move that workflow into Market Command so every system orchestrates in one
place. This change is the read-only half: what the fleet produces now lands
in TradeSync as untrusted material with provenance, on its own page. The
measuring half, each agent's claims scored against outcomes so it can earn a
weight, sits on top of this record.

## What was found (survey of 2026-09-12)

- The fleet runs in WSL Ubuntu at `~/runtimes/hermes-home`; jobs in
  `cron/jobs.json`. 43 jobs deliver to Discord, 40 deliver `local` only, and
  those 40 include the three StrikeZone full-thesis editions and the
  trade-proposal preview. **Every run is written to `cron/output/` first**,
  as `<job_id>_<stamp>.txt` and, for some jobs, `<job_id>/<stamp>.md`. That
  directory is the complete view of the fleet and needs no bot token.
- Two Discord applications already exist (ChaseOS // Hermes, ChaseOS //
  OpenClaw). The Hermes bot token lives in the runtime's `.env`.
- Pine alerts already reach Discord today: TradingView posts to per-signal
  webhooks in the StrikeZone Crypto guild (bias-flip, unikill, FVG, EMA
  cross, EQH/EQL, structure channels). Reading those channels is a second
  route for Pine evidence, alongside the tunnel Codex is building.
- The live fleet still reads and writes `chaseos_obsidian`, not the canonical
  vault. That re-pointing remains the Hermes slice's own work.

## What changed

- **Host bridge for job outputs.** `tools/hermes_output_bridge.py` scans the
  output directory over the WSL share (Docker Desktop cannot mount the
  distro here), posts every new run to `POST /state/quarantine` as source
  `chaseos` with the job's name, id, schedule and delivery target, and keeps
  a cursor on file modification time. Where a job has both forms the
  markdown is taken and the flat capture skipped. First run establishes
  "now" and reads forward. Registered as a scheduled task every two
  minutes; first real pass filed 19 runs from 12 jobs.
- **Discord reader for channel posts.** A small service polls each
  configured channel through the REST API, maps messages to submissions
  (agent label from the channel, author, content bounded and marked when
  truncated, embeds, attachments), submits oldest first as source
  `discord`, keeps cursors in Redis, establishes "now" on first sight, and
  holds a channel it cannot read for 30 minutes instead of retrying every
  pass. Never posts, never calls a model, never prints the token.
- **Channel registry.** `config/chaseos/discord-channels.json` names 27
  channels with stable labels and kinds (agent / alerts / operator); the
  reader's `DISCORD_READER_CHANNELS` is generated from it.
- **Token reuse, file to file.** `tools/copy-hermes-discord-token.ps1`
  copies the existing Hermes bot token from the runtime's `.env` into
  `runtime.env` without displaying it. `tools/set-runtime-secret.ps1` is the
  general desktop-prompt path for any other secret.
- **`discord` is a registered quarantine source.**
- **The Agents page** merges both sources, groups by agent, shows each item
  with provenance and intake verdict, and shows the advisory harness
  runtime's status and boundary.

## Live, on deploy

Reader: cursors established on the StrikeZone Hyperliquid channels
(thesis feed, evidence health, assumptions, forward test, paper outcomes,
scorecards, regime lab, upgrade approvals, model quality, cron health, ops
review, indicators). **The Pine alert channels returned HTTP 403**: the
Hermes bot is not a member of the StrikeZone Crypto guild, or lacks View
Channel / Read Message History there. That is one operator action in
Discord (invite the ChaseOS // Hermes bot to that server with those two
permissions); the reader re-checks every 30 minutes and needs no restart.
Bridge: 19 runs held after the first pass.

The advisory harness connector (`AGENT_HARNESS_URL`) is still unset: no
model runtime answered on the host. The operator should say where the
runtime is reachable before it is wired.

## What this is not

Not a mirror of the chat and not a signal path. A held item can be reviewed
and promoted only through the existing quarantine review, and an agent earns
a scoring weight only through measured skill on the evidence cards, by
operator decision.

## Tests

Root: `test_discord_evidence.py`, `test_discord_reader.py`,
`test_hermes_output.py` (filename and markdown-run parsing, delivery
labelling, bounded submission passes intake, fallback label, truncation);
`test_quarantine.py` still passes with the new source.
