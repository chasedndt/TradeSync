# Market Canvas: versioned operator drawings

Date: 2026-09-08

Branch: `codex/2026-09-01-dashboard-overhaul`

## What this is for

The Phase 4 exit gate is that **a paper trade can be reconstructed from source
observation through outcome without screenshots or memory.** The system already
retained the observation, the evidence, the decision and the outcome. What it
did not retain was the operator's own reasoning at the time — the level they
thought mattered, the note about why.

The roadmap asks for "versioned user drawings and alert rules stored
server-side". This delivers the drawings half.

## Versioned, not mutable

An edit **supersedes** rather than overwrites. `canvas_drawings` keeps every
version: the superseded row gains a `superseded_at` timestamp and stays.

This is the whole point. "What did I think at the time" is a different question
from "what do I think now", and only the second survives an overwrite. A level
revised twice reads as `v3` on the chart, so the fact that it moved is visible
rather than silently lost.

Deleting is the same: the row is marked `deleted` and superseded, and the
history endpoint still returns it.

## Validation keeps malformed shapes out of storage

`libs/tradesync_core/tradesync_core/canvas_drawings.py` validates before
anything is written, rather than leaving the renderer to cope:

| Rule | Why |
|---|---|
| Each kind declares its anchor count | A trendline with one point is not a trendline |
| Two-anchor shapes need distinct anchors | A degenerate shape renders as nothing, and usually means a double click |
| Positive finite prices, positive integer times | Infinities and booleans are not coordinates |
| A note needs a label | An empty note records nothing |
| Versions start at 1 and only increase | |

Kinds: `horizontal`, `trendline`, `range`, `note`. The UI currently places
horizontals, which the charting library supports natively as price lines; the
storage and validation already accept the other three.

## Verified live

```
create horizontal            -> v1, authority: none
edit it                      -> v2 at the new price
history                      -> v1 (superseded) AND v2 (live), both retained
malformed trendline (1 pt)   -> HTTP 400 "a trendline needs exactly 2 point(s), got 1"
delete                       -> gone from the chart, history_retained: true
history after delete         -> v1 still returned, deleted: true
```

In the Cockpit: "+ Level" arms placement, a click on the chart records a level
at that price, and it renders as a dashed line labelled with its version. A
"Your levels" list shows each with a Remove control.

## A drawing is annotation

Every response carries `authority: none`. A drawing cannot influence a score, an
admission or an execution, and nothing reads the table except the canvas.

## Tests

`tests/test_canvas_drawings.py`: 18 passed, including that a degenerate
two-point shape is refused, that a note without a label is refused, and that
versions cannot go backwards.

## Trendlines and ranges

Lightweight Charts v4 has no primitive for a two-anchor shape, so these are
projected into an SVG overlay (`DrawingOverlay.tsx`) using **the chart's own**
coordinate conversion — `timeToCoordinate` and `priceToCoordinate`.

That detail matters: the overlay never computes its own mapping. One source of
truth for scale means shapes stay pinned through pan and zoom instead of
drifting away from the candles they were placed against.

Two refusals rather than guesses:

- A shape whose anchors fall outside the visible range is **not drawn**. The
  library returns null coordinates there, and interpolating would put a line
  somewhere the operator never placed it.
- A click outside the plotted data yields no `param.time`, so placement stops.
  Falling back to "now" would anchor the shape where it was not placed.

Placement is two-click: the button reads "First point…" then "Second point…".
Two clicks on the same candle and price cancel, because the server would refuse
the degenerate shape anyway and a silent cancel is clearer than an error.

Verified live with a trendline spanning the chart — anchored at 79,950 on 6 Sep
and 78,328 on 8 Sep, it renders as a dashed diagonal following both anchors.
The `+ horizontal`, `+ trendline` and `+ range` controls each arm their own
placement mode, and the "Your annotations" list removes any of them.

## Evidence timeline

`GET /state/evidence/timeline` and a panel below the chart. This is the Phase 4
exit gate in concrete form: **a paper trade reconstructed from source
observation through outcome without screenshots or memory.**

Each entry carries:

- the call — direction, directional score, coverage, timestamps;
- **the evidence that produced it** — every contributing feature with its score
  and quality;
- **the configuration it was taken under** — catalog version and digest,
  rulebook version and digest, and the evidence digest, so a replay reproduces
  the decision exactly rather than approximately;
- the limits that applied — paper-risk multiplier and missing blocks;
- **what the market then did** — signed return, the market's own move, and best
  and worst excursion at each horizon.

An unmeasured horizon shows as pending rather than as zero, and refusals are
deliberately excluded: only an admitted call has something to reconstruct.

Verified live, e.g. `82a303bb` SHORT, score -0.4860, coverage 39.0%, catalog
`1.5.0 / c70219370fbc`, rulebook `1.0.0 / d44e7c2b8c84`, with all three
directional features contributing — including `coinbase_premium_bps`, which
confirms the promotion reaching live signals.

Coverage observed at **57.5%** shortly afterwards, above the previous 0.55
ceiling, as the premium's history accumulated.

## Outstanding in Slot 5

- Chart-native alert-rule creation.
- Funding, OI and depth overlays.

## Boundaries

`DRY_RUN=true`, `EXECUTION_ENABLED=false`. No order can be placed from the
canvas, and the footnote on the page says so.
