# Slot 1.2: Skill Measured Across Two Regimes

Date: 2026-09-08

Branch: `codex/2026-09-01-dashboard-overhaul`

## The gate

Slot 1.2 was the one hard gate in the plan: measure skill across at least two
distinct regimes, and let the result decide whether governed alerting (Slot 4)
opens at all.

Enough evidence has now accumulated to answer it. The stored window contains
both sustained declines (hours 01, 02, 05, 10 at 0% up) and genuine advances
(hours 08, 09, 13, 14 at up to +1.12%).

## Result: no demonstrable skill, in any regime, at any horizon

| Horizon | Regime | n | Hit | Market up | Expected | Skill | Significance |
|---|---|---|---|---|---|---|---|
| 15m | falling | 68 | 61.8% | 38.2% | 50.3% | **+11.4 pts** | 1.9 SE |
| 15m | rising | 76 | 57.9% | 75.0% | 61.8% | **-4.0 pts** | -0.7 SE |
| 60m | falling | 84 | 34.5% | 9.5% | 37.5% | **-2.9 pts** | -0.5 SE |
| 60m | rising | 50 | 46.0% | 74.0% | 51.0% | **-5.0 pts** | -0.7 SE |

**Nothing crosses two standard errors.** The gate returns negative: skill is not
demonstrated, so **Slot 4 does not open.**

## A correction to the earlier reading

On 2026-09-08 the pooled 60-minute figure was reported here as **-10.2 points,
-2.4 standard errors**, and described as "suggestive" of an anti-predictive
signal.

That was wrong, and the error was pooling.

```
POOLED   n=133   -10.2 pts   -2.4 SE     <- looks significant
falling  n=84     -2.9 pts   -0.5 SE     <- noise
rising   n=49     -5.0 pts   -0.7 SE     <- noise
```

A caller with a fixed directional bias, measured across windows with very
different base rates, produces an apparent effect that is an artefact of
aggregation rather than a property of the signal. This is Simpson's paradox in
its ordinary form: the pooled statistic does not describe either subgroup.

The system is **indistinguishable from chance**, not anti-predictive. The
earlier instinct to leave the signal alone rather than invert it was correct,
and for a better reason than was understood at the time.

## What the measurement tool was doing wrong

The misleading number came from the tool itself, so the fix belongs there rather
than in a one-off query. `GET /state/outcomes/by-regime` now:

- Assigns regime from the **hour's own aggregate move**, not from the individual
  outcome being scored, so the classification is not circular.
- Scores each regime against **its own baseline**.
- Reports `standard_error`, `skill_in_standard_errors` and a boolean
  `significant` at two standard errors, so a figure cannot be read as an effect
  without its uncertainty beside it.
- States in the payload that the standard error assumes independence, and that
  overlapping windows make the true uncertainty larger. It is a floor, not an
  estimate.

## What this means for the direction of the work

Two things are now established rather than suspected:

1. **Weight tuning cannot help.** Fixed-window replay showed every rulebook
   configuration either changed nothing or made things worse. Since the
   direction/suitability split, weights govern admission, not direction.
2. **The current directional evidence does not predict.** Two admitted
   directional features — `hl_return_1h_pct` and `hl_direct_cvd` — produce
   calls indistinguishable from chance in both regimes.

The lever is neither the rulebook nor the thresholds. It is **more and better
directional evidence.**

The catalog already names the next candidate: `coinbase_premium_bps` is marked
`signal_kind: directional` and `availability: unavailable`. Spot-versus-perp
premium is a genuinely different measurement from the two already admitted,
which both derive from Hyperliquid's own book and tape.

## Boundaries

`DRY_RUN=true`, `EXECUTION_ENABLED=false`. No alerting was enabled; the gate
that would permit it returned negative and Slot 4 stays closed.
