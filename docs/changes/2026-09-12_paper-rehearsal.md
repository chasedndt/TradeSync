# Paper rehearsal — preview, refuse, journal, with the gate shut

Date: 2026-09-12
Scope: `libs/tradesync_core/tradesync_core/{paper_rehearsal,risk}.py`,
migration `011_paper_rehearsals.sql`, `services/state-api/app/rehearsal.py`
(new router), `services/cockpit-ui/src/components/PaperRehearsal.tsx`, tests.

Slice 2 of the delivery sequence in Codex's 2026-09-09 review: "preview /
approve-simulated / refuse / journal path. Test duplicate submissions and
missing dependencies. This can be developed without waiting for strategy
profitability."

## The problem it solves

`/actions/preview` consults the global execution gate first. With
`EXECUTION_ENABLED=false` it refuses every plan with `EXEC_DISABLED` and
records no decision — verified live before starting. That is correct for
execution and means there was **no way to practise the decision path** without
opening the real gate.

## What was built

A rehearsal path that is structurally separate from execution:

- **Risk.** `RiskGuardian.check(phase="rehearsal")` skips only the global
  killswitch. Every per-symbol rule — DNT list, opportunity status, spread,
  impact, exposure, leverage — still applies; the point of rehearsing is to see
  those rules refuse. Preview and execute are untouched, and a test pins that.
- **Fill.** `paper_rehearsal.simulate_fill` prices a market order at the live
  mark crossing half the live spread, charging the venue's published base-tier
  taker fee (0.045%, source and read-date recorded on every fill). A missing
  spread is refused rather than assumed zero; so is a stale or missing mark.
  Each fill reports its entry cost and the move needed just to break even.
- **Journal.** `paper_rehearsals` holds one row per opportunity — rehearsed or
  refused — with the plan, the verdict, the market it was priced from and the
  fill. The unique constraint is the duplicate-submission handling: a second
  submission returns the existing row instead of a second fill.
- **Endpoint.** `POST /actions/rehearse`, `GET /state/rehearsals`, in their own
  module. A structural test asserts the module contains no reference to the
  execution service, the order route or the signer.
- **Cockpit.** A Paper rehearsal panel on the Execution page: choose a recorded
  opportunity, set a size, rehearse; the verdict, fill and costs appear, and the
  journal lists every prior rehearsal and refusal.

## Verified live (2026-09-12)

```
1) fresh   : rehearsed ETH-PERP SHORT | verdict OK | fill 2541.68 fee 0.1125 breakeven 0.047% | dup False
2) repeat  : duplicate = True | same id = True | size kept = 250.0
4) unknown : 404 Opportunity not found
5) bad size: 422
journal    : {'rehearsed': 1, 'refused': 0} | execution_authority False
```

Missing dependency (market-data unreachable) is covered by a unit test: the
rehearsal is journaled as `refused` with `MARKET_UNAVAILABLE` and no fill —
never an invented price. A consumed opportunity is refused as `DUPLICATE`.

## Tests

487 root, 58 → 62 state-api. New: seven for the fill and the rehearsal phase,
four for the endpoint (missing dependency, duplicate, gate regression,
structural no-execution-path).

## What this is not

Not a paper *portfolio*. There is no position, no exit, no P&L — a rehearsal
ends at the entry cost. The outcome measurement already answers "what did the
market do next" for every opportunity; joining the two into a costed paper
ledger is the natural next step, and it is where the fee schedule recorded on
each fill becomes an input to `edge_evidence.economic_edge`.
