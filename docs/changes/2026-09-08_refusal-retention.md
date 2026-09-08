# Bounding the refusal store without losing the denominator

Date: 2026-09-08
Scope: `libs/tradesync_core/retention.py`, `ops/migrations/008_refusal_retention.sql`,
`services/core-scorer/app/retention_job.py`, `services/state-api`

## The problem

Every scoring pass records one verdict per symbol, admitted or refused. That is
correct — the dashboard has to be able to say *why* no opportunity exists — and
it is also roughly 4,300 rows a day of full evidence JSON, kept forever. At the
time of writing: 3,603 signal rows over 1.5 days, 8.9MB, growing at about 6MB a
day with nothing to stop it. Carried in `IMPLEMENTATION_SEQUENCE.md` since
2026-09-07.

## Why deleting them is not the fix

Refusals are the **denominator**. "The coverage floor blocked 61% of ETH
verdicts last Tuesday" is only answerable if the verdicts that were *not*
admitted are counted somewhere. Delete them and every admission statistic
computed afterwards silently improves — for a system whose entire claim is that
it does not flatter itself, that is the worst available failure mode.

## The design

A refusal is **rolled up before it is removed**. `signal_refusal_daily` holds one
row per day, symbol and primary reason, carrying the count, the reason tally and
the score and coverage distribution. It is small enough to keep forever and
answers every aggregate question the full rows could. The full rows remain for
seven days, where they are actually read.

Retention never touches the rollup, and never touches an admitted signal —
those are the evidence trail behind recorded opportunities and their outcomes.

### One transaction, not two steps

The rollup and the deletion of the rows it summarises commit together. There is
no state in which rows are gone but unsummarised. The merge is also idempotent —
keyed on (day, symbol, primary reason), adding rather than replacing — so a
re-read cannot double count. Both properties are asserted.

### A multi-reason refusal is counted once

`rejection_reasons` is a list: a verdict can fail the coverage floor and the
direction band at the same time. Counting it under both codes would make the
refusal totals sum to more than the number of refusals, and an exact denominator
is the only reason this table exists.

It is filed under the **first** code — the order `decide_paper_signal` produced
them in, so the first gate the evidence actually failed. Secondary codes are not
lost: `reason_codes` tallies every code seen in the bucket. Those counts may
exceed `refusals`; `refusals` is the one that stays exact.

### Two counts, not one

A first version tracked a single `scored_rows` and weighted both means by it.
A test caught the consequence immediately: a batch of refusals carrying a
coverage but no score reported `scored_rows = 0`, so merging weighted its
coverage mean by zero and threw a real number away, returning `None`.

Score and coverage now have their own counts and each mean is recombined
weighted by its own. The regression has its own test.

### Absent is not zero

A mean is `NULL` when nothing carried the field. A mean of zero is a claim about
the scores; an absent field is not. A refusal with no stated reason is counted
under `unstated` rather than dropped, and a row with no timestamp is skipped
rather than filed under an invented day.

## Verified

Against the live database on 2026-09-08, using synthetic rows dated 29–30 days
back so no genuine evidence was eligible:

```
planted 5 synthetic refusals dated 29-30 days back
pass: {'examined': 5, 'rolled': 3, 'deleted': 5}

rollup:
  2026-08-09 coverage_below_floor   refusals=3 codes={"coverage_below_floor": 3,
                                     "score_inside_deadband": 1}
                                     scored=2 covered=3 mean_cov=0.25
                                     range=[0.21, 0.29]
  2026-08-09 score_inside_deadband  refusals=1 scored=1 covered=1 mean_cov=0.61
  2026-08-10 no_regime_evidence     refusals=1 scored=0 covered=0 mean_cov=None

synthetic rows remaining:   0 (expected 0)
rollup total refusals:      5 (expected 5)
real refusals before/after: 1468 / 1468
admitted before/after:      2168 / 2168
second pass: {'examined': 0, 'rolled': 0, 'deleted': 0}; rollup total still 5
```

Every property holds on real data: the multi-reason row counted once while its
secondary code was tallied (refusals sum to 5, codes sum to 6); `scored=2`
against `covered=3` in the same bucket, which is exactly the case the first
design lost; nothing genuine removed; a re-run a no-op.

17 unit tests in `tests/test_retention.py`. Full suite: 423 passing.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `REFUSAL_RETENTION_DAYS` | 7 | How long full refusal rows are kept |
| `RETENTION_INTERVAL_SECONDS` | 3600 | How often the pass runs |
| `RETENTION_BATCH` | 2000 | Rows per pass; a backlog drains over several |

A window below one day is refused: it would delete a refusal in the same pass
that wrote it, leaving the dashboard nothing to explain the current state with.

## Reading it

`GET /state/signals/refusal-history?days=30[&symbol=…]` returns the aggregate.
