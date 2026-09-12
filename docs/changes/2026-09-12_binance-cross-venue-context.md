# Binance funding and open interest as cross-venue context

Date: 2026-09-12
Scope: `services/market-data/app/cross_venue.py` (new), `main.py` (poller and
attach), `feature_extractor.py`, catalog **1.6.0 → 1.7.0** (three features),
tests.

Third of the three sources from the 2026-09-12 open-data research.

## What it measures

Three context-only features, all `source_authority: external_reference_venue`
and `scoring_eligible: false`:

| Feature | Kind | What it is |
|---|---|---|
| `binance_funding_rate_8h` | directional | Binance's last funding rate per 8h interval for the same coin |
| `binance_open_interest_usd` | none | Binance open interest in contracts, valued at Binance's own mark |
| `funding_spread_vs_binance_bps` | directional | Hyperliquid hourly funding × 8, minus Binance's 8h rate, in basis points |

The spread is the interesting one. Positive means Hyperliquid longs are paying
more than Binance longs for the same exposure — the Hyperliquid crowd is more
one-sidedly long than the wider market's. That is a directional *candidate*.
Like every new source it is recorded first; it can score only after
`edge_evidence.positive_skill` on its own history and an operator decision,
the path the Coinbase premium took.

## Decisions

- **Direct endpoints, not ccxt.** The research recommended `ccxt` for breadth.
  For two fields from one venue, calling Binance's public `premiumIndex` and
  `openInterest` directly is two requests per coin per minute and no new
  dependency; `ccxt` would add a large package to the image for the same two
  numbers. It remains the recommendation when more venues are wanted.
- **Alignment bound of five minutes.** Funding moves slowly, so five minutes of
  skew between the venues' readings cannot masquerade as a spread; tighter and
  a single slow poll would drop the feature for no reason. The spread carries
  its `alignment_skew_ms`.
- **Absent, never zero, per field.** OI can attach when the spread cannot
  (no Hyperliquid funding on the snapshot yet); a stale funding reading drops
  the spread without dropping OI.
- **Coverage.** All ten configured coins were confirmed listed as USDT-M
  perpetuals on Binance today. A coin Binance did not list would simply never
  get a reading.

## Verification

- 114 market-data tests pass, eleven of them for this module: the venue's
  string fields parsed strictly, OI converted at the venue mark, the per-8h
  comparison, the skew bound, independent staleness, and no `derived` key at
  all when nothing attached.
- Binance and Bybit both answered from inside the container; Bybit is not
  wired yet and would follow the same pattern.

## Live, after deploy

Regime Lab (state-api rebuilt to catalog 1.7.0), BTC-PERP:

| Feature | Value | scoring_allowed |
|---|---|---|
| `binance_funding_rate_8h` | 0.0000472 (0.0047% per 8h) | False |
| `binance_open_interest_usd` | $7.99B | False |
| `funding_spread_vs_binance_bps` | **−0.094 bps** | False |

A slightly negative spread: Hyperliquid longs paying fractionally less than
Binance longs for the same exposure at that moment. Recorded; it means nothing
until its history says otherwise.
