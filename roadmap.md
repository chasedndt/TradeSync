# TradeSync Development Roadmap

This roadmap outlines the development phases for TradeSync, broken down into parallelizable tasks suitable for multiple agents working simultaneously.

## 📅 Phase 1: Foundation & Data Ingestion
**Goal:** Establish a robust data pipeline and storage layer.

### 🟢 Track A: Infrastructure & Database
*   **Task A1:** Finalize `ops/sql/schema.sql` and ensure all necessary tables (events, signals, opportunities) are correctly defined.
*   **Task A2:** Create a database migration script/tool (e.g., using Alembic or raw Python) to manage schema changes.
*   **Task A3:** Set up a local Docker Compose environment for Postgres + Services.

### 🔵 Track B: Ingest Gateway (Data)
*   **Task B1:** Complete `services/ingest-gateway/app/main.py` to accept and validate incoming data payloads.
*   **Task B2:** Implement data normalization logic in `ingest-gateway` to convert exchange-specific formats into the standard `events` schema.
*   **Task B3:** Add support for multiple data sources (e.g., Binance, Bybit) in `data/fetch_data.py` or as separate microservices feeding the gateway.

### 🟣 Track C: Core Scorer (Logic)
*   **Task C1:** Refine `agent/core.py` to implement the "Bias Scoring" logic described in README.
*   **Task C2:** Implement unit tests for `agent/scorer.py` to verify scoring algorithms independent of live data.

---

## 🚀 Phase 2: State Management & Execution
**Goal:** Enable the system to maintain state and execute trades.

### 🟢 Track A: State API
*   **Task A4:** Develop `services/state-api` to expose the current market state (latest events, signals) via REST/gRPC.
*   **Task A5:** Implement caching (Redis?) for `state-api` to ensure low-latency access for the scorer.

### 🔵 Track B: Execution Adapters
*   **Task B4:** Implement `executor/drift_exec.py` using `driftpy` SDK.
    *   *Subtask:* Authentication & Wallet setup.
    *   *Subtask:* Order placement (Limit, Market, Oracle).
*   **Task B5:** Implement `executor/hyper_exec.py` using `hyperliquid-sdk`.
    *   *Subtask:* API signing & Order management.
*   **Task B6:** Create `executor/exec_interface.py` to enforce a common interface for all executors.

### 🟣 Track C: Signal Engine Integration
*   **Task C3:** Connect `agent/core.py` to `state-api` to fetch real-time data for scoring.
*   **Task C4:** Implement the "Decision" logic to convert Scores -> Opportunities -> Decisions -> Execution Orders.

---

## 💎 Phase 3: User Interface & Advanced Features
**Goal:** Provide visibility and advanced AI capabilities.

### 🟢 Track A: Frontend Dashboard
*   **Task A6:** Initialize a Next.js project for the dashboard.
*   **Task A7:** Build UI components to visualize:
    *   Real-time "Bias Score" charts.
    *   Active "Opportunities" and "Positions".
    *   System health/status.

### 🔵 Track B: AI & Journaling
*   **Task B7:** Implement `agent/journal.py` to log trade reasoning to the database.
*   **Task B8:** Integrate an LLM (OpenAI/Anthropic) to generate natural language explanations for signals.

### 🟣 Track C: Multi-Agent Coordination
*   **Task C5:** Implement a "Conflict Resolution" module to handle disagreeing signals from different sub-agents.

---

## 🤝 Parallel Workflows (Agent Assignments)

| Agent Role | Focus Area | Immediate Tasks |
| :--- | :--- | :--- |
| **Agent 1 (Data)** | Ingest Gateway & DB | B1, B2, A1, A2 |
| **Agent 2 (Core)** | Scoring & State | C1, C2, A4 |
| **Agent 3 (Exec)** | Execution Adapters | B4, B5, B6 |
| **Agent 4 (UI)** | Dashboard | A6, A7 |
