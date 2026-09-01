# Chapter 5 — Building the Quant System in Public

TradeSync's quant-development record can support future ChaseInTech articles, chasintech.com case studies, and LinkedIn posts, but public communication must remain evidence-led and separate from trading promotion.

## Retain for every mathematical change

- problem and operator decision;
- notation dictionary;
- formula and plain-English reading;
- source fields, units, comparator, and lookback;
- configuration version and digest;
- code commit and test command;
- paper experiment hypothesis;
- primary metric, drivers, and guardrails;
- result, uncertainty, limitations, and rejected interpretations;
- whether the work is drafted, implemented, locally tested, paper-evaluated, or promoted.

## Claim ladder

Use the narrowest truthful status:

1. **Concept documented** — explanation exists.
2. **Implemented locally** — code exists.
3. **Unit tested** — deterministic examples pass.
4. **Paper shadow running** — records are being produced without affecting decisions.
5. **Paper evaluated** — predeclared window and metrics are complete.
6. **Promoted to paper champion** — approved activation exists.

None of these statuses means profitable, production-proven, or safe for live execution.

## Public safety boundary

- Do not publish private keys, API secrets, internal paths containing sensitive identity, raw operator records, or governed ChaseOS knowledge.
- Do not describe an unvalidated backtest as expected future return.
- Separate educational explanation from financial advice.
- State data window, fees, funding, slippage, missing data, and survivorship/look-ahead controls.
- Publish failed hypotheses and limitations when they materially affect interpretation.
- Never turn a paper score into a public trade call merely to make the content more engaging.

## Suggested reusable content pattern

```text
Problem: what ambiguity were we removing?
Math: what does every symbol mean?
Implementation: what deterministic contract did we build?
Evidence: which tests and paper records exist?
Result: what changed, with uncertainty?
Limitations: what remains unknown?
Next experiment: what single hypothesis comes next?
```

Publishing itself remains a separate operator-approved action. Documentation in this repository is preparation, not publication.
