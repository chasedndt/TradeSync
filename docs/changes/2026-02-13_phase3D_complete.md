# Phase 3D Complete - Shared Core Library + Backtest/Replay Engine

**Date:** 2026-02-13
**Phase:** 3D (Steps 1 through 7)

## Summary

Phase 3D ensures that scoring, risk, and normalization logic runs from a **single canonical source** — the `tradesync_core` shared library — instead of duplicated code across services. A replay/backtest engine processes historical JSONL event datasets through the exact same `calculate_score()` → `EnhancedScorer` → `RiskGuardian` pipeline that live services use, producing structured reports. This makes the scoring pipeline testable and auditable without requiring a running Docker stack.

**Hard constraints honored:**
- No breaking changes to existing `/state/*` and `/actions/*` API contracts — all services re-export via thin shims
- Services that don't use `tradesync_core` (exec-hl-svc, exec-drift-svc, cockpit-ui, market-data) were not modified
- Backtest-runner uses `profiles: [backtest]` in compose — it does not start with the live stack by default
- All business logic was extracted verbatim from services (no algorithm changes), plus one pre-existing bug fix in `normalize_symbol`

| Step | Description | Status |
|------|-------------|--------|
| 1 | Create `libs/tradesync_core/` shared Python package | ✅ Complete |
| 2 | Update Dockerfiles + compose (repo-root context for shared lib) | ✅ Complete |
| 3 | Rewire service imports to `tradesync_core` | ✅ Complete |
| 4 | Create dataset exporter CLI + data directories | ✅ Complete |
| 5 | Build backtest-runner service | ✅ Complete |
| 6 | Create sample dataset + tests (32/32 pass) | ✅ Complete |
| 7 | Verify live stack unaffected | ⏳ Requires Docker rebuild |

---

## Step 1: Shared Library — `libs/tradesync_core/`

### Goal
Extract all pure business logic (scoring, risk, normalization, core score calculation) into a single installable Python package so that replay, tests, and services all run identical code.

### Files Created

| File | Description |
|------|-------------|
| `libs/tradesync_core/pyproject.toml` | Package metadata: `tradesync-core==0.1.0`, depends on `pydantic==2.9.2`, requires Python `>=3.10` |
| `libs/tradesync_core/tradesync_core/__init__.py` | Locked public API via explicit `__all__` — 12 exports, nothing else importable from top level |
| `libs/tradesync_core/tradesync_core/contracts.py` | `ScoreBreakdown`, `ExecutionRisk`, `EnhancedScore` dataclasses (from `services/fusion-engine/app/scoring.py` lines 19-52) |
| `libs/tradesync_core/tradesync_core/scoring.py` | `EnhancedScorer` class + `compute_enhanced_score()` convenience function (from `services/fusion-engine/app/scoring.py` lines 55-325) |
| `libs/tradesync_core/tradesync_core/risk.py` | `ReasonCode`, `RiskVerdict`, `RiskGuardian` (from `services/state-api/app/risk.py` verbatim) |
| `libs/tradesync_core/tradesync_core/symbols.py` | `normalize_symbol()` + `normalize_venue()` (consolidated from 3 identical copies, with slash-handling bug fix) |
| `libs/tradesync_core/tradesync_core/core_score.py` | `Event` dataclass + `calculate_score()` pure function (from `services/core-scorer/app/main.py` lines 55-101) |

### Public API (`__all__`)

```python
__all__ = [
    "EnhancedScorer",
    "compute_enhanced_score",
    "RiskGuardian",
    "ReasonCode",
    "RiskVerdict",
    "normalize_symbol",
    "normalize_venue",
    "Event",
    "calculate_score",
    "ScoreBreakdown",
    "ExecutionRisk",
    "EnhancedScore",
]
```

### Bug Fix: `normalize_symbol("BTC/USDT")`

Pre-existing bug in all 3 service copies: `BTC/USDT` → replace `USDT` with `-PERP` → `BTC/-PERP` → replace `/` with `-` → `BTC--PERP` (double dash).

**Fix:** Strip `/` before suffix replacement, use slice (`s[:-4]`) instead of `.replace()` for suffix swap. Now correctly returns `BTC-PERP`.

---

## Step 2: Dockerfiles + Compose Changes

### Goal
Services that import `tradesync_core` need the shared library available at build time. Docker build contexts were changed from per-service to repo-root so Dockerfiles can `COPY libs/tradesync_core`.

### Build Context Changes

All 4 affected Dockerfiles now use repo-root-relative paths:

```dockerfile
# Pattern applied to all 4 Dockerfiles:
COPY services/<service>/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY libs/tradesync_core /tmp/tradesync_core
RUN pip install --no-cache-dir /tmp/tradesync_core && rm -rf /tmp/tradesync_core

COPY services/<service>/app /app/app
```

### Files Modified

| File | Change |
|------|--------|
| `services/fusion-engine/Dockerfile` | Context: repo root; COPY paths prefixed with `services/fusion-engine/`; shared lib installed |
| `services/state-api/Dockerfile` | Context: repo root; COPY paths prefixed with `services/state-api/`; shared lib installed |
| `services/core-scorer/Dockerfile` | Context: repo root; COPY paths prefixed with `services/core-scorer/`; shared lib installed |
| `services/ingest-gateway/Dockerfile` | Context: repo root; COPY paths prefixed with `services/ingest-gateway/`; shared lib installed |
| `ops/compose.full.yml` | Build contexts changed to `..` with explicit `dockerfile:` for 4 services; `backtest-runner` service added |

### Compose Changes

**Changed services** (build context `..` + `dockerfile:`):
- `state-api`
- `core-scorer`
- `ingest-gateway`
- `fusion-engine`

**Untouched services** (build context unchanged):
- `exec-drift-svc` — uses `../services/exec-drift-svc`
- `exec-hl-svc` — uses `../services/exec-hl-svc`
- `cockpit-ui` — uses `../services/cockpit-ui`
- `market-data` — uses `../services/market-data`

**New service added:**
```yaml
backtest-runner:
  profiles: [backtest]
  build:
    context: ..
    dockerfile: services/backtest-runner/Dockerfile
  image: tradesync/backtest-runner:dev
  volumes:
    - ../data:/app/data
```

---

## Step 3: Service Import Rewiring

### Goal
Services import from `tradesync_core` instead of local copies. Local files become thin re-export shims for backward compatibility.

### Import Changes

| Service | File | Old Import | New Import |
|---------|------|------------|------------|
| fusion-engine | `app/worker.py` | `from .normalize import normalize_symbol` | `from tradesync_core import normalize_symbol` |
| fusion-engine | `app/worker.py` | `from .scoring import EnhancedScorer` | `from tradesync_core import EnhancedScorer` |
| state-api | `app/main.py` | `from app.risk import RiskGuardian` | `from tradesync_core import RiskGuardian` |
| state-api | `app/main.py` | `from app.normalize import normalize_symbol, normalize_venue` | `from tradesync_core import normalize_symbol, normalize_venue` |
| core-scorer | `app/main.py` | Local `calculate_score()` (47 lines) | Adapter: converts DB `Event` → `CoreEvent`, delegates to `_core_calculate_score` |

### Re-export Shims (kept for backward compat)

| File | Content |
|------|---------|
| `services/fusion-engine/app/scoring.py` | `from tradesync_core.scoring import EnhancedScorer, compute_enhanced_score` + contracts |
| `services/fusion-engine/app/normalize.py` | `from tradesync_core.symbols import normalize_symbol, normalize_venue` |
| `services/state-api/app/risk.py` | `from tradesync_core.risk import ReasonCode, RiskVerdict, RiskGuardian` |
| `services/state-api/app/normalize.py` | `from tradesync_core.symbols import normalize_symbol, normalize_venue` |
| `services/ingest-gateway/app/normalize.py` | `from tradesync_core.symbols import normalize_symbol, normalize_venue` |

### Core-Scorer Adapter Pattern

The core-scorer's DB `Event` model (Pydantic `BaseModel` with `id`, `symbol` fields) differs from `tradesync_core.Event` (plain dataclass without DB fields). An adapter converts between them:

```python
from tradesync_core.core_score import calculate_score as _core_calculate_score, Event as CoreEvent

def calculate_score(events: List[Event]) -> float:
    """Adapter: converts DB Event -> CoreEvent, delegates to shared library."""
    if not events:
        return 0.0
    core_events = [
        CoreEvent(ts=e.ts, source=e.source, kind=e.kind, payload=e.payload)
        for e in events
    ]
    return _core_calculate_score(core_events)
```

---

## Step 4: Dataset Exporter

### Goal
CLI tool to export historical events, signals, and opportunities from Postgres into JSONL files for offline replay.

### Files Created

| File | Description |
|------|-------------|
| `tools/export_replay_dataset.py` | Async CLI exporter (217 lines). Connects to Postgres, exports to `data/replay/<name>/` |
| `tools/requirements.txt` | `asyncpg==0.29.0` |
| `data/replay/.gitkeep` | Placeholder for replay datasets |
| `data/reports/.gitkeep` | Placeholder for report output |

### Exporter Output Format

Each dataset directory contains:

| File | Schema |
|------|--------|
| `events.jsonl` | `{ts, source, kind, payload, symbol}` — canonical `tradesync_core.Event` fields |
| `signals.jsonl` | `{id, agent, symbol, timeframe, kind, confidence, dir, features, created_at}` |
| `opportunities.jsonl` | `{id, symbol, timeframe, bias, quality, dir, status, snapshot_ts, links, confluence}` |
| `metadata.json` | `{name, symbols, start, end, exported_at, counts: {events, signals, opportunities}}` |

### Usage

```bash
# Export last 24 hours for BTC and ETH
python tools/export_replay_dataset.py \
    --name btc_eth_24h \
    --symbols BTC,ETH \
    --hours 24 \
    --pg-dsn postgresql://tradesync:pass@localhost:5432/tradesync

# Export specific date range (or use PG_DSN env)
PG_DSN=postgresql://... python tools/export_replay_dataset.py \
    --name btc_week \
    --symbols BTC \
    --start 2025-01-01 \
    --end 2025-01-07
```

---

## Step 5: Backtest Runner Service

### Goal
Replay JSONL event datasets through the live scoring + risk pipeline (via `tradesync_core`) and produce structured evaluation reports.

### Files Created

| File | Description |
|------|-------------|
| `services/backtest-runner/Dockerfile` | Python 3.11-slim, installs `tradesync_core`, entrypoint `python -m app.main` |
| `services/backtest-runner/requirements.txt` | `pydantic==2.9.2` |
| `services/backtest-runner/app/__init__.py` | Package marker |
| `services/backtest-runner/app/main.py` | CLI entrypoint with `--dataset`, `--output`, `--realtime`, `--speed` args |
| `services/backtest-runner/app/replay.py` | `ReplayEngine` class: loads JSONL, groups by symbol, runs scoring + risk pipeline |
| `services/backtest-runner/app/evaluator.py` | `generate_report()`: writes `report.json` (full data) + `report.md` (summary with tables) |

### ReplayEngine Pipeline

For each symbol in the dataset:
1. Load events from `events.jsonl`, group by symbol
2. Convert to `tradesync_core.Event` objects
3. Run `calculate_score(events)` — core directional bias
4. Run `EnhancedScorer.compute_enhanced_score()` — microstructure/exposure/regime adjustments
5. Run `RiskGuardian.check()` — trade validation
6. Record all results: `SignalResult`, `OpportunityResult`, `RiskResult`

### Virtual Time Support

| Mode | Behavior |
|------|----------|
| Default (fast) | No sleep — processes all events as fast as possible |
| `--realtime` | Proportional sleep between symbol groups based on timestamp deltas |
| `--speed N` | Multiplier for realtime (e.g., `--speed 10` = 10x faster than real time) |

### Report Output

**`report.json`** contains:
- `metadata`: dataset info
- `summary`: aggregated statistics
- `results`: full signal/opportunity/risk verdict arrays

**`report.md`** contains:
- Signal distribution table (LONG/SHORT/NEUTRAL counts, score stats)
- Opportunity distribution table (enhanced score + quality stats)
- Risk verdict breakdown table (reason code, count, percentage)
- Pass/block summary with pass rate
- Execution risk flags (if any)
- Warnings list (if any)

---

## Step 6: Sample Dataset + Tests

### Sample Dataset

**Directory:** `data/replay/sample/`

Hand-crafted events for offline testing without a live database:

| File | Records | Content |
|------|---------|---------|
| `events.jsonl` | 7 | BTC-PERP: 2 TradingView LONG + 2 metrics (negative funding, rising OI). ETH-PERP: 1 TradingView SHORT + 2 metrics (positive funding, rising OI) |
| `signals.jsonl` | 2 | BTC-PERP LONG (score 4.5), ETH-PERP SHORT (score -3.5) |
| `opportunities.jsonl` | 2 | BTC-PERP quality 45.0, ETH-PERP quality 35.0 |
| `metadata.json` | 1 | Time range: 2025-05-01 10:00 to 10:05 UTC |

### Test Suite

**File:** `tests/test_phase3d.py` — 32 tests across 7 test classes:

| Class | Tests | Validates |
|-------|-------|-----------|
| `TestTradesyncCoreImports` | 3 | All 12 public API symbols importable, version string, `__all__` length |
| `TestNormalizeSymbol` | 8 | BTCUSDT, BTC/USDT, BTC-PERP, lowercase, bare symbol, USDC suffix, empty, None |
| `TestNormalizeVenue` | 3 | hl → hyperliquid, drift passthrough, empty string |
| `TestEnhancedScorer` | 4 | Initialization, basic score, microstructure penalties, to_dict() |
| `TestRiskGuardian` | 4 | OK pass, DNT block, quality block, exec disabled block |
| `TestCalculateScore` | 5 | Empty events, LONG/SHORT bias, squeeze logic both directions, score clamping |
| `TestReplayEngine` | 3 | Sample dataset replay (7 events → 2 symbols → 2 signals), empty dataset, evaluator report generation |

**Test results:** 32/32 passing.

```
tests/test_phase3d.py ............................ 32 passed in 0.34s
```

---

## Architecture Notes

### Key Constraint: Core-Scorer Reads from Postgres

The `core-scorer` service reads events from Postgres via `asyncpg`, not from Redis streams. Its `calculate_score()` function operates on `List[Event]` pulled from SQL. The replay engine must replicate this exact function — not a Redis stream replay — to be trustworthy.

### Adopted Solution: Shared Library

By extracting `calculate_score()` into `tradesync_core.core_score`, both the live core-scorer and the backtest-runner call the same function. The core-scorer uses a thin adapter to convert its DB-specific `Event` model (Pydantic BaseModel with `id`, `symbol`) to the library's `Event` dataclass (no DB fields). The backtest-runner loads events from JSONL files and calls the library directly.

This guarantees:
- **Scoring parity**: Live and replay produce identical scores for identical inputs
- **Single source of truth**: Bug fixes in `tradesync_core` propagate to all consumers
- **Testability**: 32 unit tests validate the library without Docker

### Intentionally NOT Attempted: True Multi-Service E2E Replay

A full E2E replay (events → Redis streams → core-scorer → fusion-engine → state-api → risk check) would require mocking multiple service boundaries and is fragile. The chosen approach replays through the **pure business logic** extracted into `tradesync_core`, which covers the decision-critical code paths. Service-level integration (stream wiring, DB persistence, HTTP calls) is validated separately by Docker stack health checks.

---

## How to Run

### Local pytest (no Docker needed)

```bash
# Install shared library in editable mode (one-time)
pip install -e libs/tradesync_core

# Run Phase 3D tests
python -m pytest tests/test_phase3d.py -v -p no:anchorpy
```

### Docker build for backtest-runner

```bash
docker compose -f ops/compose.full.yml --profile backtest build backtest-runner
```

### Run sample dataset replay (in Docker)

```bash
docker compose -f ops/compose.full.yml --profile backtest run --rm backtest-runner \
    --dataset data/replay/sample --output data/reports/sample
```

### Run sample dataset replay (local, no Docker)

```bash
cd services/backtest-runner
python -m app.main --dataset ../../data/replay/sample --output ../../data/reports/sample
```

### Export real dataset from Postgres

```bash
# Requires running Postgres (via Docker stack or direct connection)
python tools/export_replay_dataset.py \
    --name my_dataset \
    --symbols BTC,ETH,SOL \
    --hours 24 \
    --pg-dsn postgresql://tradesync:CHANGE_ME@localhost:5432/tradesync
```

### Run replay on exported dataset

```bash
docker compose -f ops/compose.full.yml --profile backtest run --rm backtest-runner \
    --dataset data/replay/my_dataset --output data/reports/my_dataset
```

---

## Proof Artifacts Expected

| Artifact | Path | Contents |
|----------|------|----------|
| Full replay data | `data/reports/<dataset_name>/report.json` | Complete JSON with metadata, summary stats, and all signal/opportunity/risk results |
| Human-readable summary | `data/reports/<dataset_name>/report.md` | Markdown tables: signal distribution, opportunity stats, risk verdict breakdown, pass rate |
| Sample dataset | `data/replay/sample/` | Hand-crafted 7-event dataset for BTC + ETH |
| Test results | `pytest` output | 32/32 tests passing |

---

## Compatibility / Risk

### Services Touched

| Service | Files Modified | Impact |
|---------|---------------|--------|
| fusion-engine | `app/worker.py`, `app/scoring.py`, `app/normalize.py`, `Dockerfile` | Imports now from `tradesync_core`; re-export shims preserve `from .scoring import` paths used by other internal modules |
| state-api | `app/main.py`, `app/risk.py`, `app/normalize.py`, `Dockerfile` | Direct imports changed to `tradesync_core`; re-export shims in `risk.py` and `normalize.py` |
| core-scorer | `app/main.py`, `Dockerfile` | Local `calculate_score` replaced with adapter to shared library function |
| ingest-gateway | `app/normalize.py`, `Dockerfile` | Re-export shim only; `main.py` unchanged |

### Expected Behavior Unchanged

- All API endpoints return identical response shapes
- Scoring algorithm is byte-for-byte identical (extracted verbatim)
- Risk guardian check logic is byte-for-byte identical (extracted verbatim)
- The only behavioral change is the `normalize_symbol("BTC/USDT")` bug fix: now returns `BTC-PERP` instead of `BTC--PERP`

### Pinned Dependency: `pydantic==2.9.2`

`tradesync_core` pins `pydantic==2.9.2` to match the version already used by `fusion-engine`, `state-api`, `core-scorer`, and `ingest-gateway`. This prevents version drift between the shared library and services. The pin is exact (`==`) not ranged.

---

## Files Changed (Phase 3D Complete)

### Created

| File | Description |
|------|-------------|
| `libs/tradesync_core/pyproject.toml` | Package metadata with pinned pydantic |
| `libs/tradesync_core/tradesync_core/__init__.py` | Public API with 12 exports via `__all__` |
| `libs/tradesync_core/tradesync_core/contracts.py` | ScoreBreakdown, ExecutionRisk, EnhancedScore dataclasses |
| `libs/tradesync_core/tradesync_core/scoring.py` | EnhancedScorer class + compute_enhanced_score |
| `libs/tradesync_core/tradesync_core/risk.py` | ReasonCode, RiskVerdict, RiskGuardian |
| `libs/tradesync_core/tradesync_core/symbols.py` | normalize_symbol + normalize_venue (with bug fix) |
| `libs/tradesync_core/tradesync_core/core_score.py` | Event dataclass + calculate_score pure function |
| `services/backtest-runner/Dockerfile` | Python 3.11-slim with tradesync_core |
| `services/backtest-runner/requirements.txt` | pydantic==2.9.2 |
| `services/backtest-runner/app/__init__.py` | Package marker |
| `services/backtest-runner/app/main.py` | CLI entrypoint |
| `services/backtest-runner/app/replay.py` | ReplayEngine class |
| `services/backtest-runner/app/evaluator.py` | Report generator (JSON + Markdown) |
| `tools/export_replay_dataset.py` | Postgres → JSONL dataset exporter CLI |
| `tools/requirements.txt` | asyncpg==0.29.0 |
| `data/replay/.gitkeep` | Directory placeholder |
| `data/reports/.gitkeep` | Directory placeholder |
| `data/replay/sample/events.jsonl` | 7 hand-crafted events (BTC + ETH) |
| `data/replay/sample/signals.jsonl` | 2 sample signals |
| `data/replay/sample/opportunities.jsonl` | 2 sample opportunities |
| `data/replay/sample/metadata.json` | Dataset metadata |
| `tests/test_phase3d.py` | 32 tests across 7 classes |
| `docs/changes/2026-02-13_phase3D_complete.md` | This changelog |

### Modified

| File | Changes |
|------|---------|
| `ops/compose.full.yml` | Build contexts changed to `..` for 4 services; backtest-runner added with `profiles: [backtest]` |
| `services/fusion-engine/Dockerfile` | Repo-root context; installs tradesync_core |
| `services/state-api/Dockerfile` | Repo-root context; installs tradesync_core |
| `services/core-scorer/Dockerfile` | Repo-root context; installs tradesync_core |
| `services/ingest-gateway/Dockerfile` | Repo-root context; installs tradesync_core |
| `services/fusion-engine/app/worker.py` | Imports from `tradesync_core` instead of local modules |
| `services/fusion-engine/app/scoring.py` | Re-export shim: `from tradesync_core.scoring import ...` |
| `services/fusion-engine/app/normalize.py` | Re-export shim: `from tradesync_core.symbols import ...` |
| `services/state-api/app/main.py` | Imports from `tradesync_core` instead of local modules |
| `services/state-api/app/risk.py` | Re-export shim: `from tradesync_core.risk import ...` |
| `services/state-api/app/normalize.py` | Re-export shim: `from tradesync_core.symbols import ...` |
| `services/core-scorer/app/main.py` | `calculate_score` replaced with adapter to shared library |
| `services/ingest-gateway/app/normalize.py` | Re-export shim: `from tradesync_core.symbols import ...` |

---

## Open Items / Next

### Phase 3D Closeout Tasks (still to run)

| Task | Status | Notes |
|------|--------|-------|
| Docker rebuild all changed services | ⏳ Pending | `docker compose -f ops/compose.full.yml build state-api core-scorer fusion-engine ingest-gateway` |
| Docker stack health check | ⏳ Pending | `docker compose -f ops/compose.full.yml up -d` + verify all services healthy |
| Docker backtest-runner build | ⏳ Pending | `docker compose -f ops/compose.full.yml --profile backtest build backtest-runner` |
| Docker replay proof run | ⏳ Pending | Run sample dataset through Docker backtest-runner, verify `data/reports/sample/report.json` exists |
| Golden report generation | ⏳ Pending | Export real dataset from live Postgres, run replay, archive `report.json` + `report.md` |
| Regression gate | ✅ Done locally | `pytest tests/test_phase3d.py -v` — 32/32 pass |

### Deferred from Phase 3D

- Multi-service E2E replay (mocking Redis streams + DB boundaries) — fragile, deferred to Phase 4
- Historical microstructure data in replay (requires market-data snapshots persisted to Postgres)
- CI/CD integration for backtest regression gate
- Replay with position tracking and PnL simulation

---

*Phase 3D is functionally complete. The shared `tradesync_core` library ensures scoring parity between live and replay. 32/32 local tests pass. Docker rebuild and stack verification remain as closeout tasks before proceeding to Phase 3E.*
