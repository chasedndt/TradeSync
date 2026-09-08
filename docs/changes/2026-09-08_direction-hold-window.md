# A held direction has to be current

Date: 2026-09-08
Scope: `services/core-scorer/app/paper_producer.py`, `services/core-scorer/app/main.py`

## The defect

Hysteresis on the direction band was implemented and working: establishing or
reversing a side requires clearing `direction_enter_threshold` (0.15), while a
side already held only has to clear `direction_deadband` (0.05). That is what
stops the LONG/SHORT flipping the operator reported on 2026-09-07.

It depends entirely on knowing which side is *currently* held, and
`last_admitted_direction` returned the most recent admitted direction **ever**,
with no time bound:

```sql
SELECT dir FROM signals
WHERE agent = $1 AND symbol = $2 AND kind = 'regime_paper_signal'
ORDER BY created_at DESC LIMIT 1
```

So a side admitted once and then never again stayed "held" permanently. The
entry threshold — the entire reason hysteresis exists — stopped applying to that
symbol forever. After a quiet spell, a service restart, or a symbol that simply
stopped qualifying, a directional score of 0.06 would be admitted as a
*continuation* of a side that had not been current for days.

It was not visible in current data because the market is active and admissions
are seconds old. It would have appeared the first time it mattered.

## The fix

A held side must be recent. The bound is expressed in **scoring cycles**, not
seconds: a held side is re-admitted every cycle for as long as it clears the
hold threshold, so the meaningful question is "how many cycles of silence before
it has lapsed", and a fixed duration would silently change stickiness whenever
the cadence changed.

```python
DIRECTION_HOLD_CYCLES = 5  # DIRECTION_HOLD_CYCLES env var
direction_hold_max_age_seconds(SCORING_INTERVAL)  # 300s at the default 60s cadence
```

A lapsed side returns `None` — nothing is held, so the next direction has to
earn entry.

The unbounded query is kept for the case where no bound is given, and it is
never used by the producer.

## Verified

Against the live database with a marker symbol:

```
hold bound: 300s (5 cycles of 60s)

no admission at all            -> None
admitted 30s ago (inside 300s) -> 'LONG'
admitted 360s ago (outside)    -> None
same row, no bound             -> 'LONG'   <- the old behaviour
stale LONG then fresh SHORT    -> 'SHORT'
stale LONG then fresh NONE     -> None
```

And in production a minute after deploying, the behaviour this protects:

| symbol | kind | dir | previous | directional score |
|---|---|---|---|---|
| SOL-PERP | refusal | NONE | SHORT | −0.0248 |
| ETH-PERP | refusal | NONE | SHORT | **+0.0740** |
| BTC-PERP | signal | LONG | LONG | +0.2976 |
| SOL-PERP | signal | SHORT | SHORT | −0.0867 |

SOL held SHORT at −0.087 — below the 0.15 entry threshold, above the 0.05 hold
threshold — then fell inside the deadband at −0.025 and exited to NONE. ETH's
directional score **crossed zero** to +0.074 while holding SHORT and was refused
rather than reversed, because 0.074 does not reach the 0.15 needed to establish
the other side. That is precisely the one-minute flipping the operator objected
to, not happening.

Tests: `tests/test_paper_signal.py` covers the cycle arithmetic and refuses a
non-positive cadence, which would make the window zero and disable hysteresis.
Full suite 423 passing.
