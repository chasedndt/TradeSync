# Harness-proposed claims: the reader for the prose the rules cannot read

Date: 2026-09-13
Scope: migration `015_harness_extractions.sql`,
`libs/tradesync_core/tradesync_core/claim_proposals.py`,
`services/core-scorer/app/claims_harness.py` (+ `claims_store.harness_candidates`,
`record_harness_extraction`, one call in `claims_job.run_claims_pass`), tests.

The rule extractor abstained on 136 of the first 168 held items with "no
tracked symbol with a clear direction nearby". Most agent prose is written
that way. Now that the Hermes harness is wired in
(`changes/2026-09-13_hermes-harness-wired-and-thesis-sources.md`), it is the
reader for those rows, inside the boundary and under a verbatim check.

## How it works

- Only rows the rule reader could not read are asked about, at most four
  per five-minute pass (each ask takes tens of seconds). Empty posts,
  ledgers and alerts with no direction are settled and never sent to a
  model: asking would only invite invention.
- The question is narrow: what explicit directional calls does the post
  itself make, as a JSON array of `symbol`, `stance` (bullish or bearish),
  `horizon_minutes` and a short verbatim `quote`. None of those fields is on
  the boundary's forbidden list; the harness reports what the author said,
  it does not call a direction of its own. The ask goes through
  `POST /state/agents/harness/ask`, so the harness's answer is itself filed
  in quarantine and an answer reaching for authority is refused there.
- Every proposal is checked before it counts: tracked symbol, stance exactly
  bullish or bearish, and the quote must appear verbatim in the post and be
  neither negated nor a report of a past trade. A symbol proposed both ways
  is dropped. A proposal the harness invented cannot become a claim.
- A surviving claim belongs to the post's source, under extractor
  `harness_v1`, and is measured and carded exactly like a rule-extracted
  one. The source card does not care who read the post.
- Every ask is recorded once per row with the quarantine receipt of the
  harness answer, claims or not; a transport failure leaves the row un-asked
  for a later pass.

## Tests

Root: `test_claim_proposals.py` (prompt asks what the post said and carries
no authority words, verbatim proposals become claims under `harness_v1`, an
invented quote is rejected, a reporting or negated quote is rejected,
untracked symbol and bad stance and bad horizon handled, empty list and
non-JSON are no-claim with reasons, both-ways is dropped) and
`test_claims_harness.py` (one ask per row with the receipt kept, invented
quote recorded as no-claim, a boundary refusal is recorded and a transport
failure defers, nothing is asked when the harness is not live, embeds are
read like the rule extractor).
