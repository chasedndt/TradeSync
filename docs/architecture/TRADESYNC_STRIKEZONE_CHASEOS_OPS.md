# TradeSync × StrikeZone × ChaseOS Ops

**Status:** planning / implementation lane  
**Scope:** public-safe architecture note for the union of TradeSync, StrikeZone Crypto, and ChaseOS.  
**Authority posture:** scoring, review, risk preview, dry-run/manual readiness first; wallet/signing/autonomous live execution remains deferred until explicit gated implementation.

---

## Decision

TradeSync should operate as the **private machine cockpit** for crypto market intelligence and future execution readiness.

StrikeZone Crypto should operate as the **public/community signal and thesis surface**.

ChaseOS should operate as the **governance, evidence, approval, audit, and workflow-control plane**.

Together, the system becomes:

```text
Market evidence / source inputs
  -> ChaseOS evidence gates and workflow routing
  -> TradeSync scoring, RiskGuardian preview, opportunity lifecycle
  -> Operator review in the control plane
  -> StrikeZone public/community output only after review
  -> Dry-run/manual dispatch proof before any future live execution
```

---

## Repository ownership

### Primary implementation repo: TradeSync

Use this repository for:

- venue abstraction and executor cleanup
- scoring engine improvements
- RiskGuardian and portfolio/account risk logic
- opportunity lifecycle hardening
- cockpit UI surfaces
- dry-run/manual-dispatch simulation
- execution audit and journal substrate
- future live/autonomous trading implementation after gates are proven

### Governance/workflow repo: ChaseOS

Use the ChaseOS vault/runtime repo for:

- StrikeZone scheduled digests and evidence gates
- workflow manifests
- approval boundaries
- Discord/control-plane routing
- audit writebacks
- public/private output separation
- documentation of operator authority and safety gates

### Future runtime/product lane: Chaser Agent

Use Chaser Agent later as a business-facing/runtime lane once its 24/7 harness is ready. Do not make it the initial source of truth for TradeSync execution logic.

---

## Current role split

| System | Role | Public/private posture |
|---|---|---|
| TradeSync | Private scoring/risk/cockpit layer | Private/operator-facing |
| StrikeZone Crypto | Public/community thesis and alert surface | Public only after review |
| ChaseOS | Governance, evidence, workflow, approval, audit | Control-plane/private |
| Chaser Agent | Future runtime/business-facing operator lane | Later integration |

---

## TradeSync capabilities to keep and expand

TradeSync is valuable because its architecture already models:

- events
- signals
- opportunities
- decisions
- execution orders
- exposures
- risk checks
- circuit breakers
- dry-run execution
- cockpit UI review

This should evolve into a more correct private trading cockpit before any live execution work.

---

## Venue decision: remove Drift Protocol

TradeSync should remove Drift Protocol from the active target architecture.

Near-term venue/execution work should focus on a simplified, explicitly approved venue strategy rather than keeping Drift as a standing executor target.

Required follow-up work:

1. Remove Drift-specific active executor assumptions from docs, env examples, cockpit labels, tests, and service routing.
2. Keep historical references only where they describe prior scope or migration context.
3. Preserve the same safety gates for any replacement venue:
   - no live signing by default
   - no autonomous execution by default
   - dry-run/manual proof first
   - explicit approval for live exchange mutation
   - complete audit trail

---

## Current non-negotiable gates

The system is **not** live-autonomous-trading ready until all of the following are proven:

- runtime stack health
- repeatable build/test proof
- exposure data wired into scoring
- real position reconciliation
- fill confirmation loop
- daily notional accounting
- idempotency and circuit-breaker proof
- RiskGuardian veto persistence
- audit chain from source evidence -> signal -> opportunity -> decision -> execution result
- explicit wallet/signing/live-execution approval lane

---

## Control-plane lane model

Recommended internal control-plane lanes:

- `tradesync-strikezone-ops` — command and coordination
- `tradesync-cockpit` — scored opportunities, risk previews, blocked reasons, dry-run readiness
- `strikezone-alert-review` — public/community signal draft review
- `market-evidence` — source evidence, screenshots, funding/OI/liquidity notes
- `trade-journal` — private thesis, invalidation, decisions, post-trade review
- `trading-authority-review` — readiness packets and approval discussion

These lanes do not authorize live trading by themselves. They organize the work and preserve proof.

---

## Near-term build order

1. Public-safe architecture documentation and control-plane lane setup.
2. Drift removal/migration plan.
3. TradeSync runtime/test health check.
4. Cockpit score-breakdown and RiskGuardian visibility improvements.
5. Exposure/account risk wiring.
6. Fill confirmation and daily notional accounting.
7. StrikeZone alert-review integration from TradeSync opportunities.
8. Dry-run/manual-dispatch proof packet.
9. Only then: explicitly approved live venue/signing design.

---

## Public proof posture

This repository can show professional proof that the system is being built in public while preserving safety:

- architecture notes
- runbooks
- diagrams
- dry-run examples
- test reports
- risk gate checklists
- public-safe screenshots

Do not commit:

- Discord webhook URLs
- exchange credentials
- wallet keys
- private channel IDs if not intended for public documentation
- live account balances
- private operator notes
- unreviewed public signal copy
