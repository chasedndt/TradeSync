# Managed-paper protocol v1: test lifecycle, then test edge

Status: frozen research/engineering candidate, not a promoted profitable strategy.
Implementation: `libs/tradesync_core/tradesync_core/managed_paper.py` and
`services/state-api/app/managed_paper.py`. Strategy version:
`managed-paper-observed-quotes-v1`.

## Source-driven changes

The [Hyperliquid base fee table](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees)
was checked on 14 September. Its base perp maker charge is positive 0.015%,
not the negative 0.015% previously recorded by rehearsal metadata. That sign and
its regression expectation were corrected. Base taker remains 0.045%. This
does not infer an operator-specific fee tier, rebate, referral or staking discount.

[Hyperliquid funding](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding)
settles hourly using position size, oracle price and funding rate. Consequently,
the initial engine's fixed adverse funding charge is labelled a **scenario**,
not historical or actual settlement. Historical rates without settlement oracle
prices do not fully establish the cash flow. Reconciling those is still required.

The abstract/introduction of Bailey, Borwein, Lopez de Prado and Zhu's
[The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)
explains how repeated strategy trials create selection bias, and why an ordinary
holdout can be misleading in investment research. Our practical response is to
freeze this version, separate engineering acceptance from edge, retain failed
results and require forward evidence before promotion. This is **not** an
implementation or estimate of their CSCV/PBO method. Reading a paper is not a
strategy improvement by itself; the linked code/tests must establish the change.

## Frozen design hypotheses

| Style | ATR source | Max holding time | Stop | Target floor |
|---|---|---|---|---|
| Scalp | Closed 15m candles | 3 hours | 1.5 × ATR14 | 0.4% |
| Intraday | Closed 1h candles | 1 day | 1.5 × ATR14 | 0.8% |
| Swing | Closed 4h candles | 7 days | 2 × ATR14 | 2% |

These are engineering hypotheses, not source-proven optimal parameters. Target
distance is two stop distances, with the listed minimum used to avoid trivial
targets. The cost/reward gate can still refuse a floor-sized trade. Larger
targets do not manufacture wins or establish that a trade will reach 3%.

Entry crosses the observed ask for a long or bid for a short and applies 2 bps
additional adverse slippage. Quantity cannot exceed displayed touch size.
Exit uses the opposite executable side with adverse slippage. Fees are charged
at both simulated fills. Slippage is already in fill prices and is not deducted
again from P&L. Funding scenario: 0.125 bps per hour, always adverse, not a
guaranteed worst case. No stop is guaranteed through a gap.

Limits: BTC/ETH/SOL only, directional opportunity no older than five minutes,
up to 1,000 USDC per position, three open positions and one per symbol, planned
risk at most 50 USDC per position. No wallet, leverage expansion or live orders.
The first version is operator-opened; opening is not automatic strategy promotion.

## Observability / experiment gates

1. Preserve opportunity, ATR inputs and L2 entry observation with a digest and
   database-protected frozen plan. Evidence received later cannot be inserted
   into that original entry. Direct external as-of joins remain pending.
2. Track only received observations; reject stale/out-of-order/crossed/wide
   books and insufficient touch liquidity. A gap over 45 seconds is latched.
   Such positions cannot count as clean forward evidence. In-between touches
   are unknown; do not report an unseen target fill.
3. Engineering acceptance: deterministic lifecycle tests, real SQL entry
   immutability and restart/readback checks. Synthetic QA trades stay separate
   from performance cohorts and never populate the real portfolio.
4. Next measurement: pre-register a forward window and eligible candidate
   denominator; compare styles and entry sources after costs, including
   refusals, gaps, stale signals and sample uncertainty. Record every parameter
   revision and trial, not just the winner. The saved replay register alone
   does not capture unsuccessful/unlogged research attempts.
5. No automatic change of weights, strategy promotion or live execution from
   a good-looking replay, this lifecycle engine or an AI explanation.

## Learning exercise

Topics: algebra, percentages/basis points, time series and experimental design.
Exact Year 2 module names require the operator's syllabus.

- One basis point is 0.01%. Convert 4.5 bps into a decimal fraction: 0.00045.
- A 250 USDC position entered at 50,000 has quantity 0.005 BTC before any
  extra fill adjustment. If sold at 51,000, gross long P&L is 5 USDC.
- Work out entry fee `250 × 0.00045` and exit fee `255 × 0.00045`, then subtract
  both from 5. Explain why settled funding still matters.
- Explain why a 2% target on 250 USDC is a small dollar profit even though the
  underlying move is meaningful. Increasing size does not improve the signal.
- Explain why trying 100 weight combinations and reporting only the best
  replay is weaker evidence than one frozen rule tested on new observations.
