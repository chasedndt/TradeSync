# Claims extraction and source cards: every external source gets a track record

Date: 2026-09-12
Scope: migration `014_evidence_claims.sql`,
`libs/tradesync_core/tradesync_core/claim_extraction.py`,
`services/core-scorer/app/{claims_job,claims_store}.py` (+ `claims_loop` in `main.py`),
`services/state-api/app/source_cards.py` (`GET /state/outcomes/source-cards`),
`services/cockpit-ui/src/components/SourceCards.tsx` on the Agents page, tests.

With slice 7 accepted, three kinds of external material now land in
quarantine: TradingView / Pine alerts through the tunnel, agent posts from
the Discord channels, and every Hermes job run from the runtime. None of it
is a signal. This change gives each *source* the same treatment every
catalog feature already gets: its calls are recorded at the moment they were
made, measured against what the venue did next, and assessed with counted
independence, block bootstrap, stated costs and one Holm adjustment across
every cell. A source earns a weight the same way a feature does, or it does
not.

## What changed

- **A claim is the unit of a track record.** "This source said this
  direction on this symbol at this time." Extraction is rule-based and
  conservative: a tracked symbol (the ten-perp universe, via aliases such as
  BTCUSD, $eth, solana) and one unambiguous direction word in the same
  clause. Negation ("no trade", "invalidated") abstains; a clause that says
  both sides abstains; a report with no direction is recorded as no-claim
  with the reason. For Pine alerts the direction comes from the alert's
  action, indicator name or note, and the horizon from the chart interval
  (≤5m → 15m, ≤30m → 60m, else 240m). Agent posts and job outputs default
  to 240m. No model is involved; a harness could later propose claims
  through the same shape under its own extractor name and be measured
  identically.
- **Extraction is recorded once per held item**, claims or not, so no row
  is read twice and the operator can see why a post produced nothing.
- **Claims are measured like paper opportunities**, reusing the outcome
  job's candle fetching (1m with the 5m fallback) and its guards: a final
  "no candles" only for a window that was asked for and answered.
- **Source cards** assess every (source, horizon, polarity) cell together.
  Both polarities are tested, because a source can be usefully contrarian.
  "Earned" is positive skill that also held out of sample. The endpoint has
  no write path; cataloguing an earned source as a context-only feature and
  admitting it remains an operator decision with a change record.
- **The Agents page** shows the source cards above the feed, with the
  extraction tally (items that yielded claims, items that did not, items
  pending).

## What this means for the Pine indicators

Each indicator's alerts now accumulate a measured record under the
indicator's name (the part of the alert's `indicator` field before the
first " - "). An alert whose message names no direction is held but yields
no claim, so a Pine alert message should say `buy`/`sell` or
`bullish`/`bearish` in its `action` or `note` field to be measured. The
acceptance alert deliberately did not, and shows as no-claim with that
reason.

## Tests

Root: `test_claim_extraction.py` (aliases, direction with negation and
mixed sides, horizon by interval, a Pine alert with a direction becomes one
claim, the acceptance alert is no-claim with a reason, one claim per symbol
per clause, both-sides abstains, JSON reports yield nothing, unknown schema
refused by name), `test_claims_job.py` (extraction recorded exactly once,
measurement uses the outcome job's fetch and guards). State-api:
`test_source_cards.py` (cells by source/horizon/polarity, a skilled source
earns and a coin flip does not, a source with unmeasured claims still gets a
card, symbol filter, 503 without a pool, no write path).
