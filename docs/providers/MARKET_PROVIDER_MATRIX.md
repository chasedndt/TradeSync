# Market Provider Matrix

Last updated: 2026-09-01

This is the current provider authority map for TradeSync. Hyperliquid is the only venue. Secondary providers are free context sources and cannot affect scoring, approvals, risk, sizing, or execution.

## Authority matrix

| Provider | Cost now | Authentication | Role | Execution authority | Current state |
|---|---|---|---|---|---|
| Hyperliquid public API | Free | None for endpoints in use | Authoritative perpetual market data and sole future venue | Venue data only; never approval | Enabled |
| CoinGecko Demo API | Free | None for current endpoint | BTC/ETH/SOL aggregate spot reference | No | Enabled, context-only |
| DefiLlama API | Free | None for current endpoint | Hyperliquid protocol TVL context | No | Enabled, context-only |
| FRED API | Free | Free API key | Macro series reference | No | Wired, disabled until configured |

## Hyperliquid coverage

| Metric | State | Source / derivation | Dashboard use |
|---|---|---|---|
| Mark midpoint | REAL | `l2Book` best bid/ask midpoint | Market Pulse price |
| Current and historical funding | REAL | `metaAndAssetCtxs`, `fundingHistory` | Funding regime and horizons |
| Open interest | REAL | `metaAndAssetCtxs`, converted to USD using mark price | Current OI and horizon deltas |
| 24h notional volume | REAL | `metaAndAssetCtxs.dayNtlVlm` | Volume regime |
| L2 order book | REAL | `l2Book` | Spread, depth, imbalance, impact |
| Liquidity score | DERIVED | Normalized order-book depth and spread | Clearly labelled derived condition |
| 24h mark-price change | NOT EXPOSED BY CURRENT SNAPSHOT | Available upstream but not carried through the current contract | Displayed as unavailable, never substituted with CoinGecko |
| Direct CVD | UNAVAILABLE | Requires trade-flow ingestion | Not presented as real |
| Direct liquidation feed | UNAVAILABLE | Not in current public adapter | Not presented as real |

## Context feed contract

`GET /state/context/overview` returns:

- `role=context_only`
- `authoritative_market_source=hyperliquid`
- `execution_venue=hyperliquid`
- `execution_authority=false`
- an independent status, cache age, TTL, and failure state for every provider.

Context failures degrade only their own cards. They must not stop Hyperliquid market polling or change an execution decision.

## Configuration

```dotenv
COINGECKO_CONTEXT_ENABLED=true
COINGECKO_CONTEXT_TTL_SECONDS=300
DEFILLAMA_CONTEXT_ENABLED=true
DEFILLAMA_CONTEXT_TTL_SECONDS=900
FRED_CONTEXT_ENABLED=false
FRED_API_KEY=
FRED_SERIES=DFF,DTWEXBGS
FRED_CONTEXT_TTL_SECONDS=3600
CONTEXT_FEED_TIMEOUT_SECONDS=6
```

## Provider admission rule

Before another source can be added, document:

1. exact decision purpose;
2. free-tier limits and attribution requirements;
3. authentication and secret boundary;
4. source authority (`authoritative`, `derived`, or `context_only`);
5. cache, retry, rate-limit, and stale-data behaviour;
6. tests proving it cannot cross its authority boundary.

Solana on-chain ecosystem data is deferred to the later screener phase in `ROADMAP.md`. It is not a current venue or execution source.
