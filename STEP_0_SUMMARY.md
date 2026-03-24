# Step 0: Contract Freeze & Compatibility Summary

This document summarizes the changes made during **Step 0 — Contract Freeze + Compat**. The objective was to stabilize the API surface, standardize naming conventions, and ensure data consistency across the entire TradeSync stack.

## 🏗️ 1. Service Renaming & Docker Stabilization
The `opportunity-builder` service has been renamed to **`fusion-engine`**.

- **Files Changed**:
    - [ops/compose.full.yml](file:///c:/Users/johno/Documents/Techno%20Ubermensch/Full%20Stack%20Developing/Projects/TradeSync/ops/compose.full.yml):
        - Renamed service and container to `fusion-engine`.
        - Updated build context and image name.
        - Added a network alias `opportunity-builder` to maintain backward compatibility for internal service discovery.
    - [services/fusion-engine/app/worker.py](file:///c:/Users/johno/Documents/Techno%20Ubermensch/Full%20Stack%20Developing/Projects/TradeSync/services/fusion-engine/app/worker.py):
        - Updated Redis consumer groups and consumer names to `fusion-engine`.

---

## 🛣️ 2. API Contract Standardization
The **State API** now follows a strict canonical naming convention while maintaining support for legacy clients.

- **Canonical Endpoints**:
    - `/state/*` (e.g., `/state/snapshot`, `/state/latest/events`, `/state/opportunities`).
    - `/actions/*` (e.g., `/actions/preview`, `/actions/execute`).
- **Legacy Compatibility**:
    - Redirects and aliases added for `/opps/*`, `/preview`, `/execute`, and `/execution/status`.
    - Automated `Deprecation` and `Link` headers pointing to the new canonical successors.
- **Normalization Utilities**:
    - Created a shared normalization module in `state-api` and `fusion-engine`.
    - **Venue Alias Support**: `hl` -> `hyperliquid`, `drift` -> `drift`.
    - **Timeframe Alias Support**: `tf` -> `timeframe`.

---

## 🔤 3. Symbol Normalization (`BASE-PERP`)
Enforced a standard symbol format across the ingestion and processing layers to prevent data fragmentation.

- **Standard**: `BTC-PERP`, `SOL-PERP`, etc.
- **Impacted Services**:
    - **Ingest Gateway**:
        - [sources/hyperliquid.py](file:///c:/Users/johno/Documents/Techno%20Ubermensch/Full%20Stack%20Developing/Projects/TradeSync/services/ingest-gateway/sources/hyperliquid.py): Market poller now maps `BTC` -> `BTC-PERP`.
        - [app/main.py](file:///c:/Users/johno/Documents/Techno%20Ubermensch/Full%20Stack%20Developing/Projects/TradeSync/services/ingest-gateway/app/main.py): Webhook handler and database inserts use normalized symbols.
    - **Fusion Engine**: Worker processes events and writes opportunities using normalized symbols.
    - **State API**: Queries for events, signals, and opportunities automatically normalize input query parameters.

---

## 📓 4. Documentation & Verification
- **Route Inventory**: Created `docs/ROUTE_INVENTORY.md` listing all service endpoints.
- **Verification Runbook**: Created `docs/runbooks/Step0_Verification.md` with proof-of-work command snippets.
- **CLAUDE.md**: Updated to serve as the "Master Guide" for all 9 project containers.
- **System Docs Sync**: Updated `README.md`, `RUNBOOKS.md`, `SYSTEM_DESIGN.md`, and `AGENT_INTERFACE.md`.

### Alias to Canonical Mapping Table
| Legacy Endpoint | Standard Successor |
| :--- | :--- |
| `GET /opps` | `GET /state/opportunities` |
| `GET /opps/{id}` | `GET /state/evidence?opportunity_id={id}` |
| `POST /preview` | `POST /actions/preview` |
| `POST /execute` | `POST /actions/execute` |
| `GET /execution/status` | `GET /state/execution/status` |

---

**Step 0 is now 100% complete.** The system is standardized, documented, and fully backward compatible.

---

## 🐞 Bug Audit & Interface Gaps (Handover Notes)
During the Phase 3A (Cockpit UI) audit, the following issues were identified for immediate resolution:

1.  **"Opportunity not found" (Broken Detail View)**:
    *   **Issue**: Clicking specific signal cards in the dashboard leads to a "Not Found" state.
    *   **Cause**: likely a mismatch between the `state-api` cache and the detail query logic for ephemeral signals.
2.  **Stale Opportunity Labels**:
    *   **Issue**: 2-hour-old signals are still appearing in the "New" list.
    *   **Cause**: Frontend lacks a background "cleanup" or re-validation loop for expired signals based on the `expires_at` field.
3.  **Real-Time Data Latency**:
    *   **Issue**: Stream counters (`events.norm`) are ticking, but the Opportunity list view sometimes stalls.
    *   **Cause**: Potential polling conflict or backend filter depth issue.
4.  **Mock/Demo Execution State**:
    *   **Status**: Execution is currently in **Mock Mode** (DRY_RUN=true).
    *   **Positions**: "Live Positions" are currently deterministic demo data served by the `exec-*-svc` containers. Backend wallet configurations (Drift/Hyperliquid PKs) are **NOT** yet blueprinted or implemented.

---
Next Phase: Fixing identified UI/State bugs and proceeding to **Phase 3B: Advanced Execution**.

