# Evidence cards and earned weights

Date: 2026-09-12
Scope: migration `013_entry_features.sql`, `libs/tradesync_core/tradesync_core/{entry_features,feature_evidence}.py`,
`services/core-scorer/app/outcome_features.py` (+ one hook in `outcome_job.py`, catalog copied into the image),
`services/state-api/app/evidence_cards.py` (`GET /state/outcomes/evidence-cards`),
`services/cockpit-ui/src/components/EvidenceCards.tsx` on the Regime Lab, tests.

Slice 5 of the delivery sequence. The plan's rule was "weighted by measured
skill, not more screens": every source enters context-only and earns a scoring
weight only through its own measured track record. Until today nothing
*recorded* a context-only feature against outcomes, so nothing could ever earn
anything. The signal row keeps only the features that scored; the live feature
store keeps seven days. This slice adds the missing record and the measurement
on top of it.

## What changed

- **Entry readings are recorded, once.** For every opportunity, the outcome
  job now reads each candidate feature's stored series from `market-data` and
  writes the newest sample that was already observed at entry, within the
  feature's own freshness tolerance (one sampling bucket plus `fresh_after_ms`).
  A sample after entry is hindsight and is never used. "No current reading" is
  written as an explicit NULL row with its reason, so the job does not ask
  again and the card can count it. An opportunity older than the store's
  retention is closed out as `history expired` rather than retried forever.
  Candidates are every implemented directional feature in the catalog —
  scoring ones included, so an admitted weight faces the same test.
- **Each feature is scored as a guesser.** Its sign at entry is the direction
  it would have called (positive LONG, negative SHORT, zero abstains), scored
  against the forward return with the same `edge_evidence` machinery as the
  paper signal: counted independence, block bootstrap, three verdicts, the
  skill gate's stated costs. Both polarities are tested, because a feature
  can be usefully contrarian, and every cell of every card goes through one
  Holm adjustment so that testing twice as many cells is paid for.
- **"Earned" is defined and never self-granted.** A card is earned when one
  horizon/polarity cell shows `positive_skill` *and* that skill held on the
  chronological hold-out. The endpoint and panel report it; neither has a
  write path to the catalog (a test asserts this). Admitting a feature to
  scoring remains an operator decision made in the catalog with a change
  record, exactly as `coinbase_premium_bps` was admitted on 2026-09-08.
- **The Regime Lab shows the cards** under the skill gate: standing
  (scoring / context only), how many entries had a reading, each cell's n,
  independent windows, skill, z, hold-out and net return, and the next step
  the evidence supports.

## Live, on deploy

The first pass labelled the oldest 120 opportunities (7–8 September). Only
`hl_return_1h_pct` had readings then; the Coinbase premium and CVD series
begin on 8 September and the Binance and news-tone series on 11–12 September,
so those entries are honestly recorded as "no sample observed before entry".
The backlog of 1,479 opportunities drains at 120 per five-minute pass; new
opportunities are labelled within one pass, while their readings are fresh.

The first tolerance rule (`fresh_after_ms` alone) marked three quarters of the
one-minute feature's readings stale, because the store keeps one sample per
sampling bucket. It was corrected to bucket-plus-freshness before any card was
read from it; the 720 rows written under the wrong rule were deleted and
re-recorded the same hour.

## When Strike Zone / Pine signals enter — stated plainly

This slice is the mechanism a Pine indicator will be measured by. When the
Strike Zone alerts arrive, each indicator becomes a catalogued context-only
feature, its firings are recorded at entry like any other candidate, and its
card shows whether it earned a weight. The receiving side already exists
(`/webhook/tradingview` with HMAC and IP allowlist, quarantine intake, the
Pine → `trade_candidate_v1` adapter). **What is missing is a public route
from TradingView to this machine, and that is the next operator decision:**
either a Cloudflare Tunnel (credentials the operator holds) or a bot that
reads the existing private Discord alert channel. Nothing about Hermes is
involved; that slice stays paused. Slice 6 (the Thesis page) does not need
the route and proceeds first; the Pine stage is slice 7 and will be flagged
again the moment it is next.

## Tests

Root: `test_entry_features.py` (newest-before-entry, hindsight rejected,
stale reported with its age, tolerance rule), `test_feature_evidence.py`
(sign as call, contrarian earns inverted only, coin flip earns nothing,
every listed feature gets a card), `test_outcome_features.py` (present and
absent both written with the scoring flag at entry, an unreadable series
defers the whole opportunity, expired entries closed without a fetch, one
fetch per symbol and feature per batch, the live catalog yields the six
candidates). State-api: `test_evidence_cards.py` (standing, coverage, next
step; earned points at an operator decision; symbol filter; no pool → 503;
no write path to the catalog).
