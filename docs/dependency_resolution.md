# Dependency Conflict Resolution Report

**Date:** 2025-11-29
**Service:** Ingest Gateway

## Problem Description
The `ingest-gateway` Docker build failed during the `pip install` step with a `ResolutionImpossible` error.

**Error Log:**
```
asyncpg 0.29.0 depends on async-timeout>=4.0.3
driftpy 0.7.0 depends on async-timeout==4.0.2
→ ResolutionImpossible
```

This indicated a direct conflict between `asyncpg` (requiring a newer `async-timeout`) and `driftpy` (pinning an older version).

## Analysis
1.  **Initial Attempt:** Downgrading `asyncpg` to `0.28.0` was considered to satisfy `driftpy`'s requirement.
2.  **Secondary Conflict:** Further investigation revealed that `driftpy==0.7.0` also pinned `typing-extensions==4.4.0`, which conflicted with `pydantic==2.9.2` (requiring `typing-extensions>=4.12.2`).
3.  **Root Cause:** The `driftpy` version `0.7.0` was too old and had strict, outdated dependency pins that were incompatible with the modern stack (`fastapi`, `pydantic` v2, etc.).

## Solution
The resolution involved two key changes:

### 1. Upgrade Python Dependencies
We upgraded `driftpy` to the latest version to support modern dependencies and restored `asyncpg` to its latest version.

**File:** `services/ingest-gateway/requirements.txt`

```diff
-asyncpg==0.28.0
-driftpy==0.7.0
+asyncpg==0.29.0
+driftpy==0.8.82
```

### 2. Install Build Dependencies
The new `driftpy` version (or its dependencies like `zstandard`) requires compiling C extensions. The `python:3.11-slim` image lacks the necessary build tools, causing a `Failed building wheel for zstandard` error.

We updated the `Dockerfile` to install `build-essential` and `gcc` temporarily during the build process.

**File:** `services/ingest-gateway/Dockerfile`

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends build-essential gcc \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential gcc \
    && rm -rf /var/lib/apt/lists/*
```

## Verification
- **Command:** `docker compose -f ops/compose.full.yml build ingest-gateway`
- **Result:** Build successful. Image `tradesync/ingest-gateway:dev` created.
