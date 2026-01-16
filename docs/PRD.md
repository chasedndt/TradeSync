TradeSync — Product Requirements Document (v0.1, Audited)
1) One-liner

An always-on autonomous trading companion that ingests your vetted market feeds (TV alerts, Published Ideas, YouTube transcripts, metrics), runs specialized agents (structure/tech, funding & OI, sentiment, rotation), fuses them into a live Bias and ranked Opportunity Queue, and can explain or execute (Drift / Hyperliquid) under a strict Risk Guardian.

2) Problem

Pro traders juggle scattered feeds (X, TG, YouTube, TradingView, newsletters). Signal quality is inconsistent, context is lost, execution discipline slips, and journaling lags—leading to missed confluence and overtrading during low-quality regimes.

3) Target Users & JTBD

Active Perp Trader — “Give me one page that tells me bias, the 1–3 trades worth taking now, and why—then help me execute safely.”

Signal/Discord Operator — “Turn our alerts/research into explainable, high-quality posts with receipts.”

Builder/Researcher — “Plug in agents/strategies and compare without re-architecting.”

4) Product Goals (v0.1 scope)

Bias State per asset/TF: direction, score, regime.

Opportunity Queue (top 1–5): entry/SL/TP + management + Evidence Trail.

Copilot (chat/voice): session-aware, position-aware, evidence-first.

Execution (opt-in): Drift + Hyperliquid adapters (preview → policy check → send).

Daily Brief: changes since yesterday, top setups, risk conditions, source quality deltas.

Non-Goals v0.1: taxes, copy-trade marketplace, options, full order-book visualizers.

5) Audited Signal Sources (v0.1 Keepers)

Only these feed alerts are allowed to generate Events automatically in v0.1.

5.1 TradingView / Discord Alerts (you control these channels)

Unikill V1 (15m, 1h) — High-confluence momentum + SMC blend. (V2 excluded for now.)
Payload (example): {asset, tf, direction, entry, sl, tp1..tp3, trend_basis, risk_level, ts}

EMA 21×55 Cross (15m, 30m, 1h) — Trend shifts / momentum alignment.
Payload: {asset, tf, cross:"21_over_55" | "55_over_21", level?, ts}

Daily VWAP Close (BTC Trend Watch) — BTC closes above/below daily VWAP (trend bias anchor).
Payload: {asset:"BTC", tf:"1d_close", state:"above"|"below", price, ts}

ETHBTC Rotation — EMA-based flips / rotation bias.
Payload: {pair:"ETHBTC", tf:"1h", state:"bull"|"bear", ts}

SOL/ETH Ratio Spike (Alt-season Bot) — Risk-on rotation cue.
Payload: {ratio:"SOLETH", tf:"1h", spike:true, ts}

Combo-Confirmed FVG — Entry pings when SMC FVG aligns with momentum.
Payload: {asset, tf, tag:"combo_fvg", direction, level?, ts}

Channels like “structure-analysis” or “fakeout alerts” remain display-only until they pass audit.

5.2 Published Ideas (TradingView) → Gmail/RSS

Whitelisted authors only. Each idea email/RSS item is auto-summarized → normalized Event:
{source:"tv_idea", symbols[], tf[], stance, key_levels[], tags[], ts}.

5.3 YouTube (priority creators) → Auto transcripts

yt-dlp (audio) → Whisper (transcribe) → summarizer → Event:
{source:"yt", creator, symbols[], tf[], stance, notable_quotes[], tags[], ts}.

5.4 Single Metrics Provider (CoinAnk-like)

Funding, OI, Liquidations, (CVD where available).

Threshold rules emit Events, e.g.
{"source":"metrics","symbol":"ETH","tf":"1h","kind":"funding","value":-0.022,"state":"extreme_negative_2h"}.

5.5 Optional (later tiers)

Discord/TG (owned channels only) — Structured posts you control; forwarded Pine alerts.

X/Twitter — Official API + tiny whitelist (2–5 accts), low volume / high signal.

6) Decision Policy (end-to-end, no black boxes)

A. Normalize → Event
Every input becomes an Event: {id, ts, source, symbols[], tf[], text/stance, tags[]}.

B. Domain Agents → Signal
Agents consume Events (and/or tick reads) and emit Signals with a calibrated confidence ∈ [0,1].

Tech/Structure Agent: VWAP close, EMA trend, MSB/CHOCH, FVG reclaim.

Funding/OI Agent: funding skew, OI spikes/decay, squeeze risk.

Sentiment/Narrative Agent: YT/Ideas stance (weighted by creator Elo + recency).

Rotation/Macro Agent: ETHBTC flips, SOLETH spikes, DXY/SPX drift.

C. Fusion → Bias & Opportunity Queue
For each symbol × TF:
Bias = 0.4*Tech + 0.3*Sentiment + 0.2*RegimeFit + 0.1*Macro

RegimeFit uses recent performance of our strategy kits in the detected regime.

Opportunity Score
Opp = Bias * Confluence * (1/VolRisk) * LiquidityEdge * TimingWindow.

D. Strategy Kit → Plan
Top Opportunities become a Plan (per selected kit):
{entry, sl, tps[], management[], rationale[], strategy_kit}

Rationale is 3–6 bullets, each referencing a specific Signal/Event id.

Evidence Trail is mandatory: shows the exact TV alert / transcript snippet / metric threshold used.

E. Risk Guardian → Execute/Block
Policy checks: daily loss stop, per-symbol exposure, leverage ceiling, cooldowns, do-not-trade.

If blocked: return reason + suggested adjustment (e.g., “reduce size 30%” / “wait for funding normalize”).

If allowed: Execution adapters place/modify/cancel orders; journal entry auto-saved.

F. Learning Loop

Update source Elo (creators/indicators) and kit weights by regime using realized outcomes.

No auto-retraining on v0.1—weights update conservatively.

7) User Flows (happy paths)

Morning Prep
Open dashboard → Bias tiles (BTC/ETH/SOL) + “What changed since yesterday” → Review 1–5 Opportunities → Arm alerts or Preview orders.

Session Live
Copilot notifies bias/regime change; you ask “Do I trim SOL long?” → Copilot cites position, invalidation, funding/OI, Evidence Trail → Suggests action (Alert/Execute).

Execution (opt-in)
Preview (size, leverage, SL/TP, est. risk) → Risk Guardian checks → place or block (with reason) → journal entry saved.

Post-Session
Daily Brief → source Elo deltas, strategy performance by regime, watchlist clean-up.

8) Features & Acceptance Criteria
8.1 Bias Engine

Combines tech/structure, sentiment (creator Elo × recency), regime fit, macro drift.

AC: Bias updates ≤ 2s after new Signal; JSON available via State API; includes component weights.

8.2 Opportunity Queue

Ranks setups by confluence, vol-adjusted risk, liquidity edges, timing.

AC: Each item exposes Plan + Evidence Trail (≥3 references when available).

8.3 Evidence Trail (mandatory)

Hover/expand shows timestamps, sources, weights, and direct links/snippets.

AC: Every suggestion explainable in ≤ 1 click.

8.4 Copilot (chat/voice)

Answers “What’s the read now?”, “What changed since London/NY?”, and position questions.

AC: Always cites evidence; cannot bypass policy; can trigger Alert/Execute.

8.5 Execution (opt-in)

Drift (Solana) via driftpy. Hyperliquid via TS WS-POST service.

AC: Preview → policy check → order; dry-run default; per-exchange kill-switch; full audit log.

8.6 Risk Guardian

Daily loss stop, per-symbol exposure cap, leverage ceiling, cooldowns, DNT list.

AC: Any blocked action includes reason + actionable adjustment.

8.7 Daily Brief

Bias deltas, top opportunities, risk flags (funding extremes, OI spikes), source Elo changes.

AC: Delivered on schedule; links to Evidence.

8.8 Source Vetting & Indicator Audit

Keepers only (above list) can emit Events; others are display-only until promoted.

AC: Each source has vet status + rationale; low-cred sources get down-weighted automatically.

9) Data Acquisition & Automation

Tier-1 (v0.1):

TradingView alerts (keepers) → Discord webhooks you control → Ingest.

TradingView Published Ideas (whitelist) → Gmail/RSS → Ingest.

YouTube (priority creators) → yt-dlp + Whisper → summarizer → Ingest.

Single Metrics API (funding, OI, liqs, CVD) → threshold Events.

Tier-2 (post-MVP):

Discord/TG (owned channels) structured posts; forward Pine alerts.

Tier-3 (optional):

X/Twitter (official API + tiny whitelist).

10) Tech & Reuse (repos/patterns)

NOFX (Crypto Agent) — orchestration + unified risk model patterns → shapes our agent-runner and Risk Guardian design (we port the concepts; we don’t copy fragile code).

crypto-ai-agents — “agent zoo” pattern → our domain agents are small, single-purpose.

AI-Trader — coordinator/voting transparency → informs fusion + Evidence Trail logging.

A2A (Agent-to-Agent) — future interop (v0.2+), not in MVP.

Passivbot — Strategy Engine B (MM mode) + backtester/optimizer as a separate service for chop regimes; always behind Risk Guardian.

Hyperliquid TypeScript SDK — low-latency WS-POST + rate-limit handling → exec-hl-svc (Node/TS microservice).

HL Trading Bot (Discord) — command UX + key-handling patterns for our discord control surface.

Core stack: Python (agents, fusion, copilot), FastAPI (state/ingest), Redis Streams (events/signals/decisions), Postgres/Timescale (history), Qdrant/Pinecone (RAG), Node/TS (Hyperliquid exec svc), Whisper (ASR).

11) Metrics of Success

Adoption: ≥ 80% of live trades include complete Evidence + journal.

Latency: Alert→UI P50 ≤ 2s.

Discipline: overtrading warnings reduce day-loss incidents ≥ 30% vs baseline.

Quality: win-rate or R-multiple uplift vs prior discretionary month (per user).

12) Risks & Mitigations

Indicator unreliability → audit keepers only; live precision tracking; demote noisy sources.

Transcript variance → chunk-level + video-level summarization; low-confidence chunks flagged/excluded.

API outages → cache last-good values; degrade to tech-only mode; alert user.

Key & exec risk → isolated exec services; encrypted secrets; per-exchange kill-switch; dry-run default.

Model hallucination → evidence-first copilot; no advice without citations.

13) Release Plan

Sprint 1 (MVP) — Ingest Tier-1 (keepers + Ideas + YT + metrics) → Agent Runner → Fusion → State API → Dashboard (Bias/Opportunities/Evidence) → Discord poster → Copilot (read-only).

Sprint 2 — Execution adapters (Drift/HL) + Risk Guardian + Daily Brief + source Elo learning.

Sprint 3 — Passivbot service (MM mode) + kit backtesting/optimizer + agent/kit marketplace hooks.

14) Appendices
14.1 Event Schema (conceptual)

{id, ts, source, symbols[], tf[], text|stance, tags[]}

14.2 Signal Schema (conceptual)

{id, ts, agent_id, symbol, tf, kind, value, confidence, meta{}}

14.3 Plan Schema (conceptual)

{entry, sl, tps[], management[], rationale[], strategy_kit, evidence_ids[]}