# GDELT news tone as a context-only feature

Date: 2026-09-12
Scope: `services/market-data/app/news_tone.py` (new), `main.py` (poller and
attach), `feature_extractor.py` (mapping), catalog **1.5.0 → 1.6.0**
(`gdelt_news_tone`), tests.

Second of the three sources from the 2026-09-12 open-data research.

## Why this one

Every directional feature the scorer has today comes from the venue's own
book and tape, or from a second venue's price. None of them is *news*. The
Daily Thesis SOP put YouTube, X and screeners at Tier 5 — social context —
and the plan's first step for any new evidence class is: record it against
outcomes before believing anything about it.

GDELT was the cleanest-licensed news source the research found: free, no key,
"unlimited and unrestricted use", citation required. Its `timelinetone` mode
returns article tone (−100…+100) averaged into 15-minute buckets for a query.

## What the feature is

`gdelt_news_tone` — the newest **closed** 15-minute bucket's average tone for
news mentioning the coin. The bucket still being filled is skipped, because a
half-full bucket's average moves with every article and would read as tone
changing when only the sample was growing.

Catalog entry: block `macro_flows`, `signal_kind: directional` (tone has a
sign), **`provenance: context_only`, `source_authority: context_only`,
`scoring_eligible: false`**. The validator refuses a scoring-eligible feature
with either of those values, so this feature cannot score by accident. It
earns a weight only through `edge_evidence.positive_skill` on its recorded
history, and that promotion is an operator decision — the same path the
Coinbase premium took in 1.4.0 → 1.5.0.

## Constraints that shaped it

- **GDELT allows one request every five seconds.** The first two probes today
  were back-to-back and both got 429 with that sentence. The poller asks for
  one coin at a time, six seconds apart, on a fifteen-minute cycle: ten coins
  is ten requests per cycle, roughly a minute of polling.
- **Queries name the project, not the ticker.** "NEAR", "LINK" and "UNI" are
  ordinary words; a bare ticker would measure the tone of unrelated news.
  Each coin has an explicit query (`"NEAR protocol"`, `chainlink`,
  `"uniswap"`…), and a coin without one is skipped rather than guessed.
- **Absent, never zero.** A zero tone is a claim that the news was neutral. A
  missing reading, a malformed point, or a bucket that has not closed yields
  nothing, and a reading older than an hour is not attached to a snapshot.
- **Attribution.** GDELT's terms require citing the project; the catalog
  entry and this record do.

## Verification

- 102 market-data tests pass, including five for the parser and attach:
  newest closed bucket chosen over the one still filling; a timeline with no
  closed bucket yields None; malformed points skipped; ticker-vs-project
  queries; stale readings not attached.
- Catalog validator accepts 1.6.0 (18 features); the root catalog, regime-lab
  and paper-pipeline suites (33 tests) still pass. `macro_flows` remains an
  *uncovered* block for scoring purposes, as the existing test asserts — a
  context-only feature does not cover a block.
- The catalog edit is 28 lines added, one changed (the version); the file was
  not reformatted.

## Live, after deploy

Two more things the live API taught, both now in the code and tests:

- A six-hour window returns a bare `{}` for smaller coins (too few articles to
  build a timeline). The window is now a day; freshness still governs what is
  attached, so an hours-old bucket is absent, not stale-but-shown.
- **GDELT fills a bucket with no matching articles with a tone of exactly
  `0`**, not a gap. Read naively that is "neutral news"; it is actually "no
  news". An exactly-zero bucket is now treated as absent, and the newest
  closed bucket *with articles* is used.
- My own manual probes shared the container's IP and collided with the poller,
  which is where most of the 429s came from. The poller backs off 60s on a
  429 regardless.

state-api bakes the catalog into its image; after a rebuild the Regime Lab
reports catalog **1.7.0** (digest `ed1a467c9fe39a8e`, 21 features) and lists
`gdelt_news_tone` for BTC at **+0.4939**, `status: not_normalized`,
`scoring_allowed: False`, `provenance: context_only` — exactly the state a new
source must start in.

## Rate limiting, stated plainly

After the first cycle, GDELT refused every request from this host — at six
seconds apart, then at fifteen — including the *first* request of a cycle.
That is not spacing; it is a per-IP penalty from earlier bursts: my manual
probes during development, and the fact that each of today's several
redeploys started a fresh polling cycle the moment the container came up.

Three things now limit our own behaviour: fifteen seconds between coins, a
two-minute back-off after any refusal, and a three-minute delay before the
first cycle after startup so a rebuild is not a burst. The penalty is left to
expire on its own; nothing here retries harder. The one clean reading (BTC
+0.4939) reached the snapshot, the Regime Lab and the feature history, so the
path is proven end to end. Coverage for the other coins begins when GDELT
admits the host again, and shows as `absent` until then — never as zero.
