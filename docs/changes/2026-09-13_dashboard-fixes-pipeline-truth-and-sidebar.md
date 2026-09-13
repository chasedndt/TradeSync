# Dashboard fixes: honest pipeline nodes, the sidebar, Mission Control on one screen

Date: 2026-09-13
Scope: `services/state-api/app/integration_pipeline.py` (optional-node probes),
`graph_projection.py` (projection timeout), `economic_calendar.py` (event links),
Cockpit `Sidebar`, `Overview` + `OverviewParts`, `MarketChartPanel`, `EventsStrip`,
`tools/*` bridges (console window), scheduled tasks re-registered with `pythonw.exe`.

The operator's review of 2026-09-13, item by item.

## The terminal that kept opening and closing

Cause: the three bridge tasks (Hermes outputs, fleet snapshot, edition
renderer) were registered to run `python.exe`, which opens a console window
each time it fires, every two, five and ten minutes. Fix: the tasks now run
`pythonw.exe`, which has no window, and each script logs to
`dashboard-runtime\logs\<script>.log` when it has no console. Nothing else
in Market Command spawns a process on the host.

## Pipeline nodes that said offline or contract-only while the thing was live

The optional nodes were judged by a generic `/healthz` probe on a URL, which
none of the three connectors actually has. Each is now judged on its own
evidence:

- **TradingView + Pine** reads the receiver's configuration and the
  quarantine receipts: secret configured, public URL, accepted alerts total
  and in the last 24 hours, the latest indicator. Live when an alert arrived
  in the last day; partial when configured but quiet.
- **Strike Zone Crypto** follows the same receipts and adds how many became
  measured claims.
- **Hermes (advisory harness)**, renamed from "Agent harnesses", probes the
  Hermes API server through the connector that speaks its dialect
  (`/v1/models` with the Bearer key) and lists the models it answered with.
- **ChaseOS knowledge + Gate** reports the projected canonical-vault
  snapshot: id, node and edge counts, build time. The connector was pointed
  at the canonical vault's `07_LOGS\Graph-Snapshots` (36 snapshots present,
  newest 30 August). Projecting a 7,300-node snapshot exceeded the pool's
  statement timeout on this host; the projection now runs under a bounded
  timeout of its own.

All four read **live** on the first pass after deploy.

## Sidebar

The rail now scrolls on its own, so every entry is reachable in a short
window, and has an expand control on its edge that widens it to show each
page's name and description beside its icon. The choice is remembered per
browser. Thesis moved up to second place.

## Mission Control on one screen

- The readiness bar is a third of its former height.
- Clicking a row in the market table charts that symbol in the panel beside
  it; the timeframe chips stay on the chart.
- Paper opportunities lists the open ones with side, symbol, bias, quality
  and age, linking to each; the empty-state art is gone.
- The latest thesis edition has a card with its headline and per-symbol
  verdicts, linking to the Thesis page.
- Economic events link out: ForexFactory events open that day's calendar,
  FRED releases open FRED's release calendar.
- System health gains "Cockpit fetches": the count of this page's own
  queries that are failing, so a page with dead panels cannot say healthy.

## Tests

Calendar and pipeline suites pass with the new fields; the cockpit builds.
