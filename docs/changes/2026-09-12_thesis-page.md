# The Thesis page: the SOP's minimum valid thesis, assembled from evidence

Date: 2026-09-12
Scope: `libs/tradesync_core/tradesync_core/{thesis,thesis_context}.py`,
`services/state-api/app/thesis.py` (`GET /state/thesis?symbol=`), the
`compute_*` functions factored out of `skill_gate.py` and `evidence_cards.py`,
`services/cockpit-ui/src/pages/{Thesis,ThesisParts}.tsx` at `/thesis` in the
sidebar, tests.

Slice 6 of the delivery sequence. The Morning Thesis SOP
(`04_SOPS/Morning-Thesis-Workflow.md` in ChaseOS) asks for price structure, a
derivatives check, the macro calendar, context, a session bias with its
invalidation, and no-trade conditions. The plan's §5.2 said to render exactly
that object from evidence cards, with confidence shown as coverage and never
as win probability. This slice does that: one endpoint gathers what the
system has measured for a symbol and a pure, tested assembler turns it into
the thesis, as data and as text.

## What the thesis is made of

| Part | Source | Freshness carried |
|---|---|---|
| Chart structure | entry-time regime of the latest opportunity; the paper read (direction, directional score) | regime computed-at; signal evaluated-at |
| Paper read | the **open** paper opportunity if one is live, else the latest verdict. The producer refuses every cycle while a side is held, so the newest signal row is usually a refusal during a live read; the opportunity's expiry says what is current | evaluated-at |
| Anchor levels | 24h / 4h / 1h highs and lows and last close from 15m venue candles; partial coverage is labelled, never padded | candle count |
| Derivatives and context | current catalog readings for funding, OI, CVD, Binance funding, funding spread, Coinbase premium, news tone; absent ones say "absent" | newest observation |
| Confirmation stack | each scoring contributor's read, its catalog standing, and whether the evidence cards say it has **earned** its weight | signal evaluated-at |
| Invalidation | the trailing 1h high for a SHORT read, the 1h low for a LONG; none without a read | anchors |
| No-trade conditions | six, each stated active or clear: no demonstrated edge (skill gate), no earned inputs (cards), execution disabled, stale evidence, low coverage, High-impact event within 120 min (calendar) | now |
| Confidence | `data_coverage` — the share of rulebook weight with admissible evidence | signal evaluated-at |
| Verdict | NO TRADE while any condition is active; otherwise PAPER READ ONLY | now |

Every line names its source and age. `visibility` is `private`; the text
ends "not for publication". No model drafts any of it and a structural test
asserts the module has no path to execution or to a model.

## Live, on deploy (BTC-PERP, 18:12 UTC)

```
Verdict NO TRADE
Falling entry regime (-0.20% trailing). Paper read SHORT, score -0.45, coverage 0.52 (active paper opportunity).
Anchors 24h 76,905–77,460 · 1h 77,142–77,328 · last 77,155. Invalidation: SHORT invalid above 77,328.
Stack: return_1h SHORT, CVD LONG, Coinbase premium SHORT — all scoring, none earned.
Active: no_demonstrated_edge, no_earned_inputs, execution_disabled. Clear: stale_evidence, low_coverage, high_impact_event_near.
```

That is the honest thesis today: the system has a read, knows what would
falsify it, and says plainly why it would not trade it.

## Tests

Root: `test_thesis.py` (anchors and coverage, invalidation against the read,
stack joined to earned status, each no-trade condition active or clear, every
SOP part present and private, lines carry sources, refused and missing
inputs reported not guessed), `test_thesis_context.py`. State-api:
`test_thesis_endpoint.py` (assembly from gathered inputs, refused verdict
yields no direction, open opportunity is the current read, 503 without a
pool, no path to execution or models).

## What comes next

Slice 7 is Pine ingress. The operator chose a **Cloudflare Tunnel**, to be
implemented by Codex through its wrangler connection; when that is the only
blocker, a handover is written, committed and pushed for Codex. Slice 8, the
video edition, is a rendering of this text: chart frames from the canvas,
local TTS, ffmpeg, private Discord delivery.
