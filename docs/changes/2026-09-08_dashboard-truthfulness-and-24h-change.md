# Dashboard Truthfulness and 24h Change

Date: 2026-09-08

Branch: `codex/2026-09-01-dashboard-overhaul`

Worktree: `E:\Projects\TradeSync\dashboard-overhaul-2026-09-01`

## Repo-truth delta

Mission Control showed three things the operator could not reconcile: a 24h
change column permanently reading "deferred", a Tier A counter stuck at 4/7,
and "Scorer + opportunity fusion — OFFLINE" on the same page that displayed the
opportunities those services had just produced.

All three are now resolved and, importantly, two of them were reporting
falsehoods rather than merely missing features.

## 1. 24h change was never actually blocked

The capability gap recorded `price_change_24h` as `deferred_non_blocking`,
pending "a timestamp-aligned authoritative derivation". In fact Hyperliquid
publishes `prevDayPx` in the **same `metaAndAssetCtxs` response** that already
supplies the mark price, open interest, funding and volume this service reads
every poll. No new request, no new provider, no reconstruction from stored
history.

The value simply was never carried through. It is now:

- `providers/hyperliquid.py` captures `prevDayPx` into the price block.
- `processors/normalizer.py` carries `prev_day` onto the normalized event.
- `processors/snapshotter.py` derives `change_24h_pct` as
  `(mark - prev_day) / prev_day * 100`, and leaves both fields `None` when the
  venue omits the reference.
- `models.py` `PriceData` gained `prev_day_price_usd` and `change_24h_pct`, both
  optional.
- `Overview.tsx` renders the value with a `vs prev day` sublabel, or
  `unavailable` when null — never a flat 0%.
- The capability gap is now `implemented`, and the table footnote no longer
  claims the metric is deferred.

Verified live: BTC-PERP -1.45%, ETH-PERP -1.34%, SOL-PERP -2.66%, cross-checked
against CoinGecko's independent figures (-1.53%, -0.94%, -2.47%) — close, and
expected to differ slightly since the two use different reference points.

The lesson worth keeping: "deferred" had hardened into a fact about the product
when it was only ever a fact about the wiring. The data had been arriving in
every poll for months.

## 2. Tier A could never have reached 7/7

`ready_count` counts nodes whose status is in `HEALTHY_STATES`, which is
`{"live", "healthy"}`. But two of the seven Tier A nodes had statuses that were
incapable of ever taking those values:

```python
regime_status      = "partial" if market_live and observation_count else "offline"
performance_status = "partial" if postgres_live else "offline"
```

Neither branch can produce "live". The counter was structurally capped at 5/7,
and the operator was reading 4/7 as a diagnosis when part of it was an artefact.

Both now resolve against real evidence, using the `latest_signal_ts` and
`latest_opportunity_ts` the probe already queried but only displayed:

- `regime_engine` is **live** when market data is flowing, features are visible,
  and a *recent* signal exists — proof its evaluation actually reached storage.
  Evaluating with nothing consuming the result remains "partial", which is what
  the node's own summary always claimed.
- `performance_journal` is **live** when PostgreSQL is reachable and a recent
  signal or opportunity exists.

`_is_recent` bounds this with `PIPELINE_RECORD_FRESHNESS_SECONDS` (default 900).
Without a freshness bound a stage would keep reporting itself live on the
strength of a row written days ago — the same class of defect as a healthcheck
that only proves the port is open.

Result: **Tier A ready 7/7**.

## 3. "Scorer + opportunity fusion — OFFLINE" was not true

`CORE_SCORER_URL` and `FUSION_ENGINE_URL` defaulted to empty, so the inspector
reported the pair as unprobeable while both services were running and producing
opportunities visible elsewhere on the same screen.

The bounded override now defaults them to `http://core-scorer:8000` and
`http://fusion-engine:8002`, both verified reachable on the compose network.
Either can still be overridden or blanked by environment variable.

The reasoning: these two are `required_for_tier_a`. For a required service the
honest report when it is down is **offline**, not "not configured" — the
distinction only helps for genuinely optional connectors. `INGEST_GATEWAY_URL`
stays unset, because ingest-gateway serves the legacy events path, is not
required for Tier A, and has not been admitted.

## Tests

- `services/market-data/tests`: 37 passed (2 added for the 24h derivation,
  including one asserting a missing reference reads as `None`, never 0%).
- `services/state-api/tests/test_integration_pipeline.py` + `test_regime_lab.py`:
  12 passed (4 added for record freshness, covering recent, stale, naive-UTC and
  malformed timestamps).
- Shared suite: 105 passed.
- `npx tsc --noEmit`: passed.

`tests/test_phase3c.py::test_macro_headlines_endpoint` and
`test_macro_headlines_structure` failed once with `httpx.ReadTimeout` and passed
on re-run. They call an external endpoint and are network-flaky, not affected by
this slice.

## Boundaries observed

`DRY_RUN` and `EXECUTION_ENABLED` unchanged. No wallet, no order, no credential,
no deployment, no public exposure. The operator runtime env file was not read or
modified — the probe defaults live in the repository's compose override, where
they can be reviewed.
