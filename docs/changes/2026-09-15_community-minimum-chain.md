# 2026-09-15 — Community Server jobs at their once-daily minimum (Hermes compute)

Operator instruction: every ChaseOS Community Server Hermes job keeps running at its minimum daily
recurring loop, at most once a day, and none is paused. Operator decision the same night: the StrikeZone
material-change watch and director-thesis runs, and core-scorer's harness claim reading, stay on because
TradeSync uses both.

## Measured before the change (24 hours to 14 September 23:10 UTC)

- StrikeZone director-thesis chats launched by scripts: 20 sessions, 4.1M new and 22.6M cached tokens.
- Core-scorer harness claim reading (`api_server`): 348 sessions, 3.7M new and 3.3M cached tokens.
- Cron agent jobs: 10.2M tokens (45.1M over 7 days), almost all ChaseOS Community and Growth social jobs.

## Applied (fleet directives through the Hermes gateway's jobs API; each keeps the value it replaced)

- 15 September, the announcement chain's twice-daily stages run once a day, each stage reading the one
  before: evidence drop 08:30 (was 08:30 and 15:30), intake 08:40 (was 08:40 and 15:40), announcement
  draft 08:45, campaign control 09:15, server announcement draft 09:33, publisher 10:05 (was 10:05 and 17:05).
- 14 September 23:35 UTC, 15 other Community and Growth agent jobs were paused, which was not the
  instruction. The operator corrected it and all 15 were resumed on 15 September at 00:17 UTC on their own
  schedules: ten daily (orchestrators, X and LinkedIn curators, blog curator, combined previews, final
  campaign review), the acquisition planner (Monday, Wednesday, Friday), the poster studio (Monday and
  Thursday), the research scout (Monday), the growth funnel review and the weekly recap (Friday).
- Eleven jobs that were already paused before this work (commercial-ops lanes, campaign adapters, visual
  proof, admin approval summary) were left as found.
- Expected saving: about 1M agent tokens a day, from the intake's and publisher's second daily runs;
  every other Community job already ran at most once a day.

## Code (state-api, deployed)

- `fleet.py` split into `fleet_models.py`, `fleet_rules.py` and `fleet_store.py` without behaviour change
  (`2b7c05c`; 417 to 259 lines).
- Schedule directives accept an exact daily time, `daily-HHMM`, on the fleet host's clock (`76d0a42`), so
  a chain keeps its order when a second daily run is dropped. State-api tests: 284 passed.

## Side effects and undo

- While the 15 jobs were paused, the social automation health watchdog posted one "Action Required" card
  (00:57 BST) listing ten disabled stages. With them resumed, its next run posts "Social Automation Health
  Restored" and then stays silent.
- Any job can be resumed, and any schedule set back, from the Fleet page.
