# Phase 0 — Resource and Runtime Readiness

Status: FOUNDATION IMPLEMENTED / CURRENT HOST BLOCKED FOR CORE START.

## Purpose

This pass adds a read-only readiness gate and a lean Docker Compose overlay for ChaseOS Market Command. It does not start Docker, WSL, Ollama, TradeSync services, a wallet, or any execution path.

## Run the audit

```powershell
powershell -ExecutionPolicy Bypass -File ops\scripts\market-command-readiness.ps1 -Json
```

Evidence is written by default to:

`E:\ChaseOSBuilds\market-command-phase0-resource-audit\evidence`

To use the result as a hard pre-start gate:

```powershell
powershell -ExecutionPolicy Bypass -File ops\scripts\market-command-readiness.ps1 -EnforceCoreStartGate -Json
```

Exit code `2` means the core profile must not start. The audit never starts a service.

## Lean Compose overlay

Validate the merged configuration:

```powershell
docker compose -f ops\compose.full.yml -f ops\compose.market-command.yml config
```

The default merged profile contains the lean deterministic paper core:

- PostgreSQL
- Redis
- Hyperliquid market data
- ingest gateway
- core scorer
- fusion engine
- state API

Optional profiles:

| Profile | Adds | Default |
|---|---|---|
| `operator` | Cockpit UI | off |
| `evidence` | Qdrant | off |
| `paper-exec` | dry-run Hyperliquid boundary | off |
| `analytics` | backtest runner | off |

Ollama remains outside Docker and is never started by this Compose overlay.

## Resource budget

The lean core container limits total 3.25 GiB. Reservations total approximately 1.63 GiB. These are initial ceilings, not measured steady-state proof. Phase 0 must measure actual per-service usage before adjustment. The current host `.wslconfig` ceiling remains 6 GiB; this pass did not mutate it.

The core gate requires:

- `E:` mounted as `ChaseOS_Runtime` on NTFS;
- at least 10 GiB and 5% free;
- external Docker VHDX present;
- Ollama model root on E and no C-drive model cache;
- host RAM at or below 65%;
- sampled CPU at or below 30%;
- valid TradeSync Git metadata;
- Docker engine running.

The audit also reports a separate `docker_engine_start_allowed` gate. This omits the circular requirement that Docker already be running, so the operator can determine whether it is safe to start Docker Desktop before attempting the core profile.

## Current live result — 2026-08-23

- E: PASS — 753.32 GiB free, 80.87%.
- Host resources: BLOCKED — 84.3% RAM and 100% sampled CPU during the initial live audit.
- Docker: stopped.
- Ubuntu WSL: stopped.
- Ollama: unreachable.
- Git: blocked by a stale worktree pointer to a missing parent repository.
- Execution: disabled and unauthorized.
- Docker engine start: blocked until memory/CPU and Git readiness pass.

The next safe action is to reduce the Windows baseline, repair Git deliberately, and rerun the audit. Do not start the stack until the enforced gate passes.
