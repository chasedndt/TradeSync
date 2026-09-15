# State-api mutating routes — 15 September 2026

Every route that changes state at `db27305`, what authorised it before
`claude/security-review`, and what any caller that reached the port could do with it.

I found them by searching `services/state-api/app` for POST, PUT, PATCH and DELETE
registrations in every form: `@app.post`, `@router.post` and `app.post(path)(handler)`.
Paths are under `services/state-api/app/` unless shown in full. Findings: H2 and H3 in
[the review](2026-09-15_local-access-review.md).

## Before this branch

Two checks existed, and nothing else was checked:
- The mobile controls require `X-API-Key` to equal `MOBILE_ALERTS_CONTROL_KEY`
  (`mobile_alerts.py:29-33`). They answer 503 while it is unset, as it was on 15 September.
- The webhook authenticates each alert with the shared secret in its body
  (`libs/tradesync_core/tradesync_core/tradingview_webhook.py:138-146`).

| Area | Routes (file:line) | What any caller could do |
|---|---|---|
| Paper | `POST /state/paper-control` (`managed_paper.py:84`), `/state/paper-positions` (`:160`), `/state/paper-positions/{id}/close` (`:225`), `/state/research-trials` (`:132`) | Resume entries, open and close paper positions, register trials |
| Learning | `POST /state/learning/proposals/generate` (`learning_actions.py:38`), `…/{id}/adopt` (`:50`), `…/{id}/reject` (`:68`), `/state/learning/active/revert` (`:86`) | Change the paper scorer's weights; `confirm` is a body field |
| Hermes fleet | `POST /state/fleet/directives` (`fleet.py:182`), `…/directives/report` (`:237`), `/state/fleet/snapshot` (`:74`) | Pause, resume, run, re-schedule or redirect a job at once through the gateway (`fleet.py:196-198`); rewrite its working directory, which the bridge writes into `jobs.json` (`fleet_rules.py:58-61`, `tools/hermes_fleet_bridge.py:173-176`); overwrite the fleet read model |
| Hermes compute | `POST /state/agents/harness/ask` (`main.py:2524`), `/state/market/horizons/reading` (`horizons.py:264`), `…/horizons/refresh` (`:254`), `/state/thesis/editions/generate` (`editions.py:256`) | Spend model time |
| Evidence and intake | `POST /state/quarantine` (`main.py:1299`), `…/{id}/review` (`:1896`), `…/{id}/extract-candidate` (`:1817`), `/state/knowledge/gate/authorize-paper-evaluation` (`:1736`), `/state/knowledge/graph/ingest` (`:2669`), `/state/strikezone/ingest` (`strikezone_ingest.py:79`), `/state/thesis/editions/{id}/media` (`editions.py:232`) | Poison evidence, promote quarantined items, record approval envelopes |
| Regime Lab, research | `POST /state/regime-lab/experiments` (`regime_lab_routes.py:120`), `/state/regime-lab/replay` (`regime_replay.py:247`), `/state/trade-research/replay` (`trade_research.py:74`) | Store drafts, run replays |
| Canvas | `POST`, `PUT`, `DELETE /state/canvas/drawings…` (`canvas_drawings.py:151,173,215,235`) | Create, change and delete drawings |
| Actions | `POST /actions/preview` (`main.py:800`), `/actions/execute` (`:1024`), `/actions/rehearse` (`rehearsal.py:77`), legacy `/preview` and `/execute` (`main.py:3210,3215`) | Record decisions and paper orders; the execution gate stays closed |
| Mobile alerts | six `POST /state/mobile-alerts/…` routes (`mobile_alerts.py:179-241`) | Nothing without the control key |
| TradingView | `POST /webhook/tradingview` (`main.py:1956`) | Nothing without the body secret |

Notes:
- Opportunities have no mutating route (`opportunities_routes.py:29,92` are GETs).
- GET routes are not guarded. Those reviewed for side effects only query: the harness,
  Hermes, signer status and preflight probes.
- File-serving routes accept bare names or exact patterns only: `editions.py:246-254`,
  `strikezone_lab.py:200-208`, `main.py:2697-2702`.

## After this branch

- **Origin check.** Every route above except `/webhook/tradingview` refuses, with 403 before
  the route runs, a change sent from a web page other than the Cockpit.
- **Operator token.** With `STATE_API_OPERATOR_TOKEN` set, each of those routes also needs
  `X-Operator-Token`.
- **Later routes.** The guard wraps the whole application (`services/state-api/app/asgi.py`), so
  routes added elsewhere are covered without changes. One example is
  `PUT /state/market/horizons/reading-schedule` (`reading_schedule.py:127` on
  `codex/2026-09-01-dashboard-overhaul` at `2a0d748`). The Cockpit sends it through `apiPut`
  (`src/api/hooks/useReadingSchedule.ts:22`), so it carries the Cockpit's origin and, once
  configured, the token.
- **Callers that send the token when it is configured:**
  - host tools: `tools/hermes_fleet_bridge.py`, `hermes_output_bridge.py`,
    `strikezone_quant_bridge.py`, `thesis_video.py`;
  - containers: `services/core-scorer/app/claims_harness.py`,
    `services/discord-reader/app/main.py`;
  - state-api's own calls: `editions.py`, `horizon_reading.py`;
  - the Cockpit: `services/cockpit-ui/src/api/credentials.ts`.
