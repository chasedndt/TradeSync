# 2026-09-15 — Community Server minimum chain (Hermes compute)

Operator instruction: cut the ChaseOS Community Server's Hermes cron jobs to the minimum daily chain.
Operator decision the same night: the StrikeZone material-change watch and director-thesis runs, and
core-scorer's harness claim reading, stay on because TradeSync uses both. Nothing else was changed.

## Measured before the change (24 hours to 14 September 23:10 UTC)

- StrikeZone director-thesis chats launched by scripts: 20 sessions, 4.1M new and 22.6M cached tokens.
- Core-scorer harness claim reading (`api_server`): 348 sessions, 3.7M new and 3.3M cached tokens.
- Cron agent jobs: 10.2M tokens (45.1M over 7 days), almost all ChaseOS Community and Growth social jobs.

## Applied (fleet directives through the Hermes gateway's jobs API; each keeps the value it replaced)

- 14 September 23:35 UTC, paused 15 Community and Growth agent jobs: Growth Manager daily social
  orchestration, final campaign review, ChaseInTech social orchestrator, ChaseOS and ChaseInTech X
  curators, ChaseOS and founder LinkedIn curators, ChaseOS.ai blog campaign curator, ChaseOS and
  ChaseInTech combined post previews, acquisition campaign planner, growth funnel review,
  evidence-to-poster campaign studio, Growth Manager research and policy scout, weekly community recap
  draft. Together they used 5.9M tokens in the measured 24 hours.
- 15 September, the announcement chain runs once a day, each stage reading the one before: evidence drop
  08:30 (was 08:30 and 15:30), intake 08:40 (was 08:40 and 15:40), announcement draft 08:45, campaign
  control 09:15, server announcement draft 09:33, publisher 10:05 (was 10:05 and 17:05).
- Expected saving: about 5M to 7M agent tokens a day (the higher figure on days the weekly jobs ran).

## Code (state-api, deployed)

- `fleet.py` split into `fleet_models.py`, `fleet_rules.py` and `fleet_store.py` without behaviour change
  (`2b7c05c`; 417 to 259 lines).
- Schedule directives accept an exact daily time, `daily-HHMM`, on the fleet host's clock (`76d0a42`), so
  a chain keeps its order when a second daily run is dropped. State-api tests: 284 passed.

## Side effects and undo

- The social automation health watchdog monitors ten of the paused stages. When it next runs it posts one
  "workflow stage is disabled" card to the Community workflow status channel, then stays silent while the
  set of findings is unchanged.
- Any job can be resumed, and any schedule set back, from the Fleet page.
