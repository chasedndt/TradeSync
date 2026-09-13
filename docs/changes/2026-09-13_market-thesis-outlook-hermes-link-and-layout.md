# Market Thesis with outlook and measured event reactions, the Hermes link, and the layout fixes

Date: 2026-09-13
Scope: migration `018_outlook_and_hermes_link.sql`;
`libs/tradesync_core/tradesync_core/{event_reactions,market_outlook,outlook_render}.py`;
`services/state-api/app/{hermes_link,event_outlook,editions,fleet,integration_pipeline}.py`;
Cockpit `Sidebar`, `Overview` with `components/home/*`, `EventsStrip`, `pages/Thesis` with
`components/thesis/*`, `components/agents/HermesPanel`, `pages/Execution`, canvas markers;
`tools/{hermes_fleet_bridge,thesis_video}.py`; `nginx.conf` read timeout 90 s.

The operator's second review of 2026-09-13. Each point, and what changed.

## Hermes read as offline while it was running

Cause: the pipeline called Hermes's authenticated `/v1/models` on every read
with a three-second timeout. Hermes answers `/health` in about 0.35 s, but a
busy gateway takes longer on the authenticated route, so the node flipped to
offline. Fix: `hermes_link` keeps a heartbeat instead. Every 15 s it calls
`/health` (8 s timeout), every 60 s `/v1/models` with the key, and keeps the
last answer, latency, version, consecutive failures and the last 40 results.
Everything that shows Hermes (pipeline node, readiness bar, Agents page)
reads that memory and never makes its own request. Live means an answer
within 60 s; degraded means reachable but the key or a platform failing.

The fleet bridge now also posts Hermes's own `gateway_state.json`, so the
dashboard shows the API server and Discord platform states separately (the
Discord platform has been retrying while the API server stayed connected).

The node is renamed **Hermes gateway**, described as what it is (the fleet's
scheduler, Discord platform and API server), and its evidence lists host and
port, version, seconds since the last answer, latency, recent availability,
models and platform states. `GET /state/hermes/status` serves the same.

## Hermes panel with its trading jobs

The Agents page (now "Hermes & agents") opens with the gateway: status,
`host:port`, version, last answer, latency, availability, heartbeat strip,
platform states, and every trading job (StrikeZone, Hyperliquid quant lab,
thesis, proposals, evidence) with its schedule and enable/disable control,
applied by the fleet bridge with a backup.

## The Market Thesis

**An outlook comes first.** Each edition now carries: the breadth of the
paper reads across the universe (bearish, bullish, mixed or none, with the
counts, labelled as a description of the evidence), the lead reads for BTC
and ETH with invalidation levels, trader notes, and this week's High-impact
and market-moving events.

**Every event says how the market reacted before.** For CPI, PPI, the jobs
report, retail sales, GDP, PCE and jobless claims, past release dates come
from FRED (release ids verified live); FOMC decision days come from the Fed's
published calendar, because FRED's FOMC series updates daily. For each past
release the move from the last hourly close before the release to the close
1, 4 and 24 hours later is measured on Hyperliquid candles over 180 days,
beside the same move at the same hour on days with no release within a day.
The event shows the median move, the multiple of an ordinary move, the share
of up moves and the sample size, and one plain sentence of guidance (for
example: stand aside or cut size into the release, and give stops more than
the median range). With fewer than four occurrences it says so instead.

**Matching an event to its record.** Calendars reuse titles, so a title
alone is not enough. On the first live read, Canada's "CPI m/m" and its
median, trimmed and common CPI measures, and Switzerland's "PPI m/m", all
carried US CPI and US PPI guidance, and FRED's daily "FOMC Press Release"
entries on 14 and 15 September were treated as the FOMC decision, which falls
on 16 September. An event now takes a kind only when its title, its country
(every measured kind is a US release) and, for FOMC, one of the Fed's
published decision days all fit; meeting minutes no longer count as a
decision. Variants of one release at one instant (CPI m/m, Core CPI m/m) are
one key event listing the others, so the reaction and its guidance appear
once, and the events strip gives each variant row the same reaction chip.
GDP and PCE share their release days in this window, so their measured
reactions are identical by construction.

**The week actually reaches the thesis.** The calendar payload held 296
events but served the first 60 by time, and FRED's daily data series (Daily
Treasury Inflation-Indexed Securities, Federal Funds Data, FOMC Press Release,
Key ECB Interest Rates) matched the market-moving keywords, filled 45 of those
60 rows and made a Treasury series the "next market-moving event". Nothing
after 15 September reached the thesis or the events strip, so the FOMC
decision on the 16th was missing. Now a FRED release is market-moving only
if it is one of the measured releases (by FRED release id) or a keyword match
that is not listed on three or more dates in the window; FRED is read with
room for the whole week; the cut keeps every High or market-moving event first
and fills the rest in time order; and FOMC decision days come from the Fed's
calendar at 2 pm Eastern (`app/fed_calendar.py`) wherever the week's feed does
not already list the decision.

Reading the corrected week back showed the rest: Switzerland's PPI was the
"next market-moving event" and FRED's Treasury capital-flow series was
market-moving. Central-bank keywords now count for any country, data-release
keywords only for US releases, "treasury" is no longer a keyword and jobless
claims are. One kind on one day is one key event (the FOMC statement and its
press conference, FRED's date-only retail sales card and the feed's timed
one), led by the card that has a time of day; FRED's spelled-out retail sales
and weekly claims titles map to their kinds. An unmeasured country's bundle at
one minute (Canada's CPI m/m, median and trimmed CPI; the Bank of England's
rate, votes and summary) is one key event too, and the trader notes for the
next 48 hours lead with events that have a measured record and name the
country of any non-US release.

**Articles.** Recent coverage of each scheduled kind comes from GDELT's
article list, cached three hours, spaced and backed off so a rate limit
yields no articles rather than an error. Links open in the browser.

**Hermes briefing.** Each edition asks Hermes, through the harness boundary,
for a four-paragraph briefing from the measured outlook only. It is filed in
quarantine with a receipt and shown as advisory. A refusal or timeout is
shown as such; the rest of the edition stands.

**Regenerate.** "Regenerate thesis" (with an optional reason, stored on the
edition) starts a background job; building ten markets, the outlook and the
briefing takes minutes, and the cockpit proxy cuts requests at 90 s, so the
page polls the job's stage instead of waiting on a request.

**Formatting.** The Thesis page renders the edition instead of dumping
text: the outlook with a reads bar and lead-read cards, this week's events
as cards with reaction tables, guidance and links, the briefing, every
market as a card (verdict, read, regime, levels, invalidation, coverage bar,
derivatives, blocking conditions), the narrated video, and the written text
and spoken script behind a disclosure. The live single-market read stays
below, on demand.

## Mission Control layout

- Readiness is one thin line: market data, pipeline, Hermes, execution.
- **Market Thesis** sits directly under it: lean, reads bar, notes, lead reads,
  next event with its guidance, regenerate, link to the full thesis.
- **Market Pulse** no longer has a chart beside it. Clicking a market opens its
  chart underneath the row, with 5m, 15m, 1h and 4h chips.
- **This week** sits beside Market Pulse, collapsible (remembered), and each
  market-moving event opens to its reaction table, guidance and articles.
- **Paper Opportunities** is full width below, as a table with links.
- Context and system health (now including Hermes and this page's own failing
  fetches) at the bottom.

## Sidebar

The expand control is a full-width bar at the foot of the rail with a clear
hover state, replacing the small edge button. The rail defaults to expanded,
scrolls on its own, and no longer carries notifications, settings, operator
or sign-out: this is a single-operator workstation.

## Execution Readiness

Rebuilt on its own stylesheet (the old page mixed utility classes). It is a
gate checklist, each gate with its requirement and what is measured now:
runtime gate, demonstrated edge (from the skill gate), paper rehearsal
journal, isolated wallet and signer, executor, single-use approval and canary
limits, with a count of gates met. The watch-only wallet and paper rehearsal
sit side by side below.

## Canvas signals

Research-signal markers used to label every candle with a call, which buried
the chart. Now only a change of side is drawn, as an arrow labelled with the
side; "Every call" adds the held candles as small unlabelled dots.

## Tests

Root: `test_event_reactions.py` (title mapping, US Eastern release time with
daylight saving, window measured from the close before the release and
refused across gaps, profile against ordinary days, baseline exclusion,
guidance with sample size), `test_market_outlook.py` (breadth leans, key
events with reaction guidance and articles, notes, text and narration).
State-api suite passes with the editions job, outlook and heartbeat.
