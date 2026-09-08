# Test suite repair and the `app` package collision

<!-- venue-guard-exempt: discusses the removed venue by name
     explains why the substring scan was narrowed, and gives real reappearances as examples -->

Date: 2026-09-08
Scope: `tests/`, `services/ingest-gateway`, `services/backtest-runner`,
`tools/run_tests.py`, `pytest.ini`

## What was wrong

Every service in this repository packages its code as `app`. A Python process
can hold only one module named `app`, so whichever test file sorted first and
inserted its service directory onto `sys.path` silently decided what `app` meant
for the entire run. Nothing was wrong with the code under test; the suite was
answering questions about the wrong service.

The symptom was order dependence. `tests/test_phase3d.py` passed 32/32 on its
own and failed 4 in a whole-directory run, because `test_market_data_math.py`
sorts earlier and claimed `app` for market-data first.

Chasing that down surfaced six further defects, four of them in shipped code
rather than in tests.

## Defects found and fixed

### 1. `app` name collision (test wiring)

`tests/_service_import.py` loads a service under a private alias
(`market_data_app`, `backtest_runner_app`, `core_scorer_app`,
`ingest_gateway_app`) with an explicit `__path__`, so its own relative imports
still resolve and no test claims the global name. The five affected root test
files now use it.

### 2. `services/ingest-gateway/app/models` was unimportable (shipped code)

`app/models.py` **and** `app/models/` both existed. Python resolves a regular
module before a namespace-package directory, so `app.models` always meant the
flat file, and every `from .models.market import ...` raised
`'app.models' is not a package`. That made `app/ingest.py` and
`app/collectors/hyperliquid.py` dead code **inside the container**, not only in
tests — they could never have been imported.

`NormalizedEvent` was also declared identically in both places, which is the
duplication that eventually drifts apart.

Fixed: `app/models/` is now a real package with one model per file
(`event.py`, `alert.py`, `market.py`) and a thin `__init__.py` registry.
`app/models.py` is deleted. `from app.models import NormalizedEvent` still
works, and `from app.models.market import MarketSnapshot` now works too.

### 3. `services/ingest-gateway` depended on two global names (shipped code)

`app/main.py` did `from sources.hyperliquid import ...`, and
`sources/hyperliquid.py` did `from app.models import ...`. Both resolved only
because the Dockerfile copied the two directories side by side and put their
parent on `PYTHONPATH`. The service was unimportable anywhere else.

`sources/` moved to `app/sources/` and both imports became relative. The
Dockerfile no longer copies a second tree.

Verified in the built image:

```
$ docker run --rm -e PYTHONPATH=/app tradesync/ingest-gateway:dev python -c "..."
import graph ok: TradeSync Ingest Gateway
models: app.models.event app.models.alert app.models.market
```

`app.ingest` and `app.collectors.hyperliquid` import for the first time.

### 4. `services/backtest-runner` imported itself absolutely (shipped code)

`app/evaluator.py` and `app/main.py` used `from app.replay import ...` — a
package referring to itself by a global name it does not own. Now relative.

### 5. The removed-venue guard had been red at HEAD

`tests/test_hyperliquid_only.py` scanned every tracked file for the substring
`drift`. That name is also an ordinary English noun and this codebase uses it
constantly — documentation drift, clock drift, policy drift. The guard fired on
prose in `docs/CHASEOS_MARKET_COMMAND_HANDOVER.md`, which has been tracked with
that wording since before the guard existed, so the test has been failing at
HEAD and telling the operator nothing.

The scan now looks for the name used **as a name**: part of a longer token
(`driftpy`, `drift_client`, `exec-drift-svc`), a quoted or dotted literal, or
directly adjacent to venue vocabulary. `test_the_guard_still_recognises_a_real_venue_reference`
asserts seven realistic reappearances are caught and five legitimate prose uses
are not, so the narrowing cannot silently become a no-op.

### 6. Every funding test was scoring an empty list (test correctness)

`tests/test_core_scorer.py` built funding events with `source="hyperliquid"`,
`kind="snapshot"`. `calculate_score` reads `source == "metrics"` and
`kind == "market_snapshot"`, and `fetch_events` selects on exactly those values,
so none of those events would ever have reached the scorer in production either.

Two tests failed; the rest passed by coincidence (a clamped score is 10.0
whether or not the funding term contributes). The tests also asserted the
opposite sign convention to the one implemented: positive funding means longs
are paying shorts, so the crowd is long and the bias is short.

Rewritten against the real contract, including the ±0.5 base bias, the 0.5%
open-interest threshold for the squeeze term, a case just below that threshold,
and the fact that funding is read from the newest snapshot regardless of input
order.

### 7. `services/state-api` reported a gate it was not reading

Three rejection paths returned `execution_enabled=True` as a literal while
`EXECUTION_ENABLED=false`. They now call `execution_gate_enabled()`. This was
found by rewriting the stale `test_execute_action`, which had asserted a
`placed_dry_run` status that Phase 3C replaced.

### 8. market-data's compose healthcheck assertion was stale

`tests/test_phase0_resource_readiness.py` asserted a `/healthz` probe. The
service is now gated on `/readyz`, deliberately: `/healthz` says the process is
alive, `/readyz` says its data is fresh enough to serve, and compose's
`condition: service_healthy` is a readiness question. On 7 Sept the process
stayed up while its feed had stalled and a `/healthz` probe called it healthy
throughout.

## Running the tests

The service suites under `services/*/tests` are deliberately written against
`app`, because that is how each service imports itself inside its container.
Keeping that property means they cannot share a process. `tools/run_tests.py`
gives each suite its own:

```
$ python tools/run_tests.py
summary
  ok   root         278 passed, 2 warnings, 10 subtests passed in 30.95s
  ok   state-api    34 passed in 7.59s
  ok   market-data  73 passed in 1.47s
  ok   exec-hl-svc  3 passed in 1.57s
```

`pytest.ini` sets `testpaths = tests` so a bare `pytest` at the root runs the
cross-service suite rather than collecting the service suites together and
producing confident nonsense.

388 tests, all green. Before this pass a whole-directory run could not complete
collection.
