# Liquidity-source comparison v1 — experimental, not promoted

## Dashboard acceptance — 14 September, 01:46 BST

Signal Ledger now renders the read-only comparison by holding style, with eligible
denominators, coverage, selected/skipped counts, baseline/filter means and paired
difference. Rule/exclusions/limitations are expandable. The live empty cohort is
explicitly unmeasured. The existing dashboard hierarchy guided the comparison's
same-denominator presentation and source-coverage labels.

`npm run build` passed (Vite 19.16s; existing bundle/dependency warnings).
cockpit-ui rebuilt/replaced locally. Extended `tools/qa_managed_paper_ui.cjs`
passed at 1366/375px, checking live empty and labelled populated fixture comparison,
100 bps fixture arithmetic, existing paper controls, no page errors/document
overflow. Phone fixture screenshot inspected under
`E:/Visual QA/TradeSync Visual QA/Current Reviews/2026-09-14-source-comparison`.
Wide tables scroll within the panel. No live trade/outcome or backend change.

Immutable trial registration, forward observations and broader source evaluation
remain open. No secret, delivery, wallet, strategy promotion, commit or push.

## API implementation / activity — 14 September, 01:43 BST

Codex preserved the dirty branch; E: 342 GB free. Added malformed-record guards
and read-only `GET /state/paper-positions/source-comparison`, capped at the latest
1,000 entries with truncation metadata and separate scalp/intraday/swing cohorts.
No source weights or portfolio rows are changed by this endpoint.

Verification: **653 root tests and 174 State API tests passed** (17 integration
tests deselected; two existing warnings). State API rebuilt/replaced locally.
Live readback returned zero eligible rows and null comparison means, not evidence
of zero returns or an edge. No frontend change, secret, message, wallet, commit or
push. Five pure comparison tests now cover fixture arithmetic and malformed data.
Next: UI and immutable registration before collecting new forward evidence.

Frozen candidate definition: `book-alignment-ablation-v1`, 14 September 2026.
Implementation: `tradesync_core/source_comparison.py`. This definition has not
been evaluated on actual managed-paper outcomes; current tests use fixtures.

## Question and hypothesis

Among the same clean closed managed-paper trades, would abstaining when displayed
book notional fails to align with trade direction improve average net simulated
return per original opportunity? This is a descriptive retrospective comparison,
not proof of causality or a prospective, independently registered trial.

The source is the latest frozen pre-entry Hyperliquid book-history sample, no
older than 30 seconds at entry. It contains at most the displayed top ten levels
on each side. It is not all market liquidity, executable depth or liquidation risk.

## Fixed rule and mathematics

Let **B** be summed bid notional and **A** summed ask notional in that sample.
Book imbalance is **(B − A) / (B + A)**. This is a normalized difference (algebra
and ratios), between −1 and +1 for positive B and A. It is not a probability.
For a long, keep its sign; for a short, reverse it. That gives directional alignment.

Candidate rule: retain the hypothetical trade only when alignment is at least
**0.2**. This threshold is an experimental choice, not a literature-calibrated
constant. Missing/stale/future context abstains and is counted separately.

Per-trade return in basis points = **net simulated USDC / entry notional × 10,000**.
1 basis point is 0.01%. Both means use the **same original eligible opportunity
count**. An abstained trade contributes zero to the filter mean, not a removed
denominator. The reported difference is the average paired filter-minus-baseline
return. This is not account equity return or a compounded capital simulation.

## Eligibility and limitations

Only closed outcomes explicitly marked without observation gaps, finite net
results and positive notionals enter the comparison. Duplicate/missing IDs and
invalid outcomes are counted as exclusions. No eligible trades yields unavailable
means, not zero performance. Operator selection, overlapping positions, funding
scenarios, source coverage and repeated hypothesis inspection limit inference.
No confidence interval, significance, automatic promotion or live weight update.

Changing the rule requires a new version. Retain losing and rejected variants.
Before claiming forward evidence, persist the registration time and specification
digest, admit only later entries and implement an immutable trial registry; that
registry is **not yet implemented**. The earlier research protocol discusses
backtest selection bias; this small ablation is not a replacement for its gates.

## Learning exercise

Topics: algebraic ratios, weighted/paired means, missing-data selection bias and
experimental design. Your exact Year 2 module mapping awaits the actual syllabus.

1. With B=70 and A=30, compute imbalance; repeat for a short.
2. Two baseline trades return +100 and −200 bps. The filter takes only the first.
   Calculate both means using two original opportunities, then their difference.
3. Explain why averaging only the retained trade answers a different question.
4. Explain why these two trades cannot establish predictive skill, even with a
   positive paired difference. What changes if the rejected trade has no context?

Next implementation: API/UI readback grouped by holding style, robust input
validation, trial registration and genuine forward observations.
