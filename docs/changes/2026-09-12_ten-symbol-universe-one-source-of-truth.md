# Ten-symbol universe, configured once

Date: 2026-09-12
Scope: `ops/compose.full.yml`, `services/core-scorer/app/main.py`,
`services/ingest-gateway/app/sources/hyperliquid.py`,
`services/market-data/app/main.py` (`/snapshots` order),
`services/cockpit-ui/src/api/hooks/useTrackedSymbols.ts` and the four pages
that used to carry their own list.

## What the operator asked

"Three pairs is not gonna be enough forever" — more of Hyperliquid's
high-volume pairs.

## The rule, then the list

Hyperliquid's `metaAndAssetCtxs` was ranked by 24-hour notional volume on
2026-09-12 (178 live markets). Selection rule: **24h notional ≥ $30M and max
leverage ≥ 10×**. Leverage is a proxy for the venue's own view of a market's
depth and maturity; the volume floor keeps the order-book and outcome
measurements meaningful.

| # | Coin | 24h notional | Open interest |
|---|---|---|---|
| 1 | BTC | $3.64B | $2.76B |
| 2 | ETH | $2.59B | $2.46B |
| 3 | HYPE | $596M | $1.66B |
| 4 | ZEC | $519M | $535M |
| 5 | SOL | $311M | $539M |
| 6 | XRP | $103M | $216M |
| 7 | NEAR | $77M | $147M |
| 8 | PUMP | $76M | $145M |
| 9 | LINK | $33M | $73M |
| 10 | UNI | $31M | $46M |

The rule is the authority, not the list. Review monthly against the same
query; PUMP and ZEC are the two most likely to fall out.

## One source of truth

The list existed in **seven places**: an env default in market-data, a
*different* env (`SYMBOLS`, bare coins) in core-scorer, a constant in
ingest-gateway, and constants in four Cockpit files (Mission Control, Market
Canvas, Regime Lab, the chart panel). Adding a pair meant finding all seven;
the ones missed would show a stale list while the API served more.

Now:

- `ops/compose.full.yml` declares `x-market-symbols` once as a YAML anchor and
  passes it as `MARKET_SYMBOLS` to market-data and core-scorer. Verified with
  `docker compose config`: both services receive the same ten.
- core-scorer and ingest-gateway read `MARKET_SYMBOLS` and strip `-PERP`
  themselves rather than keeping a second, divergent list.
- The Cockpit derives its symbols from `/state/market/snapshots` through one
  hook, `useTrackedSymbols()`, with the classic three as a fallback only
  while loading. No page holds a symbol constant.
- `/snapshots` sorts in the configured order. Redis `KEYS` is arbitrary, and
  the first deploy rendered BTC, LINK, UNI, ETH… — correct data in a
  meaningless order.

## Load

- The context poll is **one** request for every symbol, so it scales for free.
- The order-book poll is one request **per symbol**. At 3s, ten symbols would
  ask for 200/min. `POLL_INTERVAL_ORDERBOOK` is now 10000ms (60/min) against a
  limiter whose base is 120/min. The limiter reported no back-off after the
  change.
- market-data after rollout: 64MB of a 512MB cap, 13.5% CPU; Redis 81MB of
  256MB. The earlier 218MB reading was the same container after four days
  up, so the wider list has not raised the floor.

## Coverage, not substitution

The spot-premium feature reads Coinbase spot. Coins Coinbase does not list get
no premium value; that appears as lower `data_coverage` for those symbols,
never as a substituted number. That is the existing contract doing its job.

## Verification

- `docker compose config`: both services show the ten-symbol `MARKET_SYMBOLS`;
  `POLL_INTERVAL_ORDERBOOK: "10000"`.
- Python suites touched (core-scorer, ingest-gateway): 19 passed. Cockpit
  `npm run build`: passed.
- market-data `/status` reports all ten; `/snapshots` count 10; `/readyz` 200;
  every symbol's snapshot age 4.3–4.9s three minutes after rollout.
- Signals in the first five minutes: BTC/ETH/SOL 5 each, the seven new coins
  2 each (they started mid-window).
- Mission Control, Market Canvas and the chart panel render all ten in the
  browser. The STALE badge visible in the first screenshot was the
  market-data restart transient; every symbol was fresh on re-read.

## What widening the universe does to the measurement

Seven new symbols enter the outcome sample from today. Per-symbol skill is
available (`/state/outcomes/by-regime?symbol=`), and the independence code
already pools symbols conservatively. But the pooled cells now mix a
three-symbol history with a ten-symbol present; any comparison across the
09-12 boundary should say so.
