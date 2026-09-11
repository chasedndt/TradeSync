# The outcome job fetches the windows it measures

Date: 2026-09-11 / 12
Scope: `services/core-scorer/app/{outcome_job,outcome_windows}.py`,
`services/market-data/app/candles.py` (+ `/candles` route), tests.

## What was wrong

Found while re-measuring gate 1.2 after a 27-hour Docker outage: the 240-minute
horizon had not recorded a single new outcome since 8 September, 824 windows
sat `pending` although they had closed days earlier, and the job logged
`reviewed 40 opportunities, 0 horizons measured` every five minutes.

Three defects, one root cause — the job asked the venue for "the last 480
one-minute candles" instead of for the windows it was measuring:

1. **Windows older than eight hours found no candles and were written off.**
   `insufficient_candles` is a final verdict. After the outage every window
   that closed during it — 79 at 15m, 79 at 60m, 63 at 240m — was stamped
   "no candles cover this window", although Hyperliquid had the candles and
   had never been asked for them.
2. **The selection query counted only `measured` as finished**, so those
   wrongly-final rows still qualified as unfinished, and because it took the
   forty *newest*, the same forty post-outage rows were re-reviewed forever.
   The 824 genuinely pending rows behind them were never reached.
3. There was **no way to ask market-data for an explicit range** — the
   `/candles` route only understood "latest N".

## What changed

- `market-data /candles` accepts `start_ms`/`end_ms`. A range wider than the
  1,000-candle cap is refused with "split the range", not silently truncated
  into a partial window that looks complete.
- `outcome_windows.py`: the span every pending window needs, chunked to the cap
  with abutting chunks, merged by open time, and `window_was_requested` — true
  only when every second of a window fell inside a *received* chunk.
- `outcome_job.py`: fetches per symbol for the batch's real span; a final "no
  candles" can only be written when the window was requested and answered,
  otherwise the row stays `pending`; `insufficient_candles` counts as finished;
  oldest first, batch 120, so a backlog drains instead of ageing.

### Then a second finding: the venue's own retention

The first corrected pass still measured nothing. Probed directly:

| Age of window | 1m candles | 5m | 15m |
|---|---|---|---|
| 12h – 72h ago | 61 | 13 | 5 |
| 96h ago | **0** | 13 | 5 |

**Hyperliquid serves 1-minute candles for roughly three days; 5-minute ones
persist.** So an outage under ~3 days is fully recoverable at 1m, and older
windows are recoverable only at 5m.

The job now falls back to 5m when a *successfully requested* 1m span comes back
empty — an empty answer, never a failed request. Two rules apply:

- A horizon measured at 5m says so in its `reason`, so a 5m-entry result is
  never averaged with 1m ones unknowingly.
- **15m horizons are not measured at 5m.** Entry is the first candle at or
  after the signal; a 5m candle can place it up to a third of a 15m window
  late, which is a different measurement. Those rows stay honestly
  unmeasured with the reason stated.

## Verification

- 476 cross-service tests pass, including 24 new ones. Among them: a window
  from yesterday judged against an 8-hour fetch is *not* evidence of a gap; a
  ten-minute sample, an outage and ten more minutes is two windows, not
  seventeen; a failed middle chunk disqualifies a window that straddles it; a
  15m horizon at 5m is refused; a 60m one is measured and labelled.
- Deployed: market-data then core-scorer, sequentially, `--no-deps`.
- 221 wrongly-final rows reset to pending after the first deploy; the 120
  rows the venue has no 1m history for reset again after the fallback deploy.
  Re-measurement results are recorded below once the passes complete.

## Re-measurement results (2026-09-12, after both deploys)

Two passes on the per-window build, 120 rows each: 240 then 322 horizons measured.

| Window age | 15m | 60m | 240m |
|---|---|---|---|
| Older than ~3 days (278 windows) | `insufficient_candles` — "5m is too coarse for a 15m horizon" | measured at 5m, labelled | measured at 5m, labelled |
| Newer (164 windows) | measured at 1m | measured at 1m | measured at 1m |

Totals moved from 74 → **516 measured at 240m** with 664 still draining; 60m
from 882 → 1,121. Nothing was written off for a window that was not requested.

**Follow-up needed:** `/state/outcomes/by-regime` does not yet distinguish rows
measured at 5m from those at 1m. Until it does, treat 60m/240m cells that
include pre-09-09 windows as mixed-resolution. The row-level `reason` carries
the fact; the aggregate should read it.

## What this means for the gate

The 240m horizon's evidence since 8 September was never lost — it was never
fetched. As the backlog drains, the 240m cells will gain their first real
independent windows. Nothing about the verdict changes until they do.
