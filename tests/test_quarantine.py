"""Quarantine intake tests.

This is the boundary every Tier B connector crosses. Its whole purpose is that
untrusted material cannot become evidence by simply arriving, so these tests
assert refusals as carefully as acceptances.
"""

import unittest

from tradesync_core.quarantine import (
    MAX_PAYLOAD_BYTES,
    QuarantineError,
    content_digest,
    evaluate_submission,
    promotion_blockers,
)

NOW = 1_788_800_000_000


def _payload(**extra):
    base = {"ticker": "BTCUSD", "interval": "15m", "action": "buy", "price": 79000}
    base.update(extra)
    return base


def _evaluate(source="tradingview", payload=None, **kw):
    return evaluate_submission(
        source, payload if payload is not None else _payload(), NOW, **kw
    )


class AcceptanceTests(unittest.TestCase):
    def test_a_well_formed_submission_from_a_known_source_is_accepted(self):
        verdict = _evaluate()
        self.assertTrue(verdict.accepted)
        self.assertEqual(verdict.reasons, [])
        self.assertEqual(verdict.normalized["ticker"], "BTCUSD")

    def test_acceptance_still_confers_no_authority(self):
        """Entering quarantine is not admission to the catalog."""
        payload = _evaluate().to_dict()
        self.assertEqual(payload["authority"], "none")
        self.assertEqual(payload["tier"], "B")

    def test_a_rejected_submission_carries_no_normalized_content(self):
        verdict = _evaluate(source="who_is_this")
        self.assertFalse(verdict.accepted)
        self.assertEqual(verdict.normalized, {})


class RefusalTests(unittest.TestCase):
    def test_an_unregistered_source_is_refused(self):
        verdict = _evaluate(source="random_service")
        self.assertIn("unknown_source", [r["code"] for r in verdict.reasons])

    def test_a_payload_may_not_claim_its_own_authority(self):
        """Privilege escalation by assertion is the obvious attack."""
        for field in ("admitted", "execution_authority", "scoring_allowed", "provenance"):
            with self.subTest(field=field):
                verdict = _evaluate(payload=_payload(**{field: True}))
                self.assertFalse(verdict.accepted)
                reason = next(
                    r for r in verdict.reasons if r["code"] == "payload_claims_authority"
                )
                self.assertIn(field, reason["detail"])

    def test_multiple_claimed_fields_are_all_named(self):
        verdict = _evaluate(payload=_payload(admitted=True, trust="high"))
        reason = next(
            r for r in verdict.reasons if r["code"] == "payload_claims_authority"
        )
        self.assertIn("admitted", reason["detail"])
        self.assertIn("trust", reason["detail"])

    def test_an_oversized_payload_is_refused(self):
        verdict = _evaluate(payload=_payload(blob="x" * (MAX_PAYLOAD_BYTES + 10)))
        self.assertIn("payload_too_large", [r["code"] for r in verdict.reasons])

    def test_a_duplicate_resubmission_is_refused(self):
        first = _evaluate()
        again = _evaluate(seen_digests=[first.content_digest])
        self.assertFalse(again.accepted)
        self.assertIn("duplicate_submission", [r["code"] for r in again.reasons])

    def test_a_stale_submission_is_refused(self):
        verdict = _evaluate(observed_at_ms=NOW - 3_600_000)
        self.assertIn("submission_stale", [r["code"] for r in verdict.reasons])

    def test_a_future_dated_submission_is_refused(self):
        verdict = _evaluate(observed_at_ms=NOW + 600_000)
        self.assertIn("timestamped_in_future", [r["code"] for r in verdict.reasons])

    def test_small_clock_skew_is_tolerated(self):
        """Real senders drift; only implausible futures are refused."""
        self.assertTrue(_evaluate(observed_at_ms=NOW + 30_000).accepted)

    def test_malformed_calls_raise_rather_than_silently_refusing(self):
        with self.assertRaises(QuarantineError):
            evaluate_submission("tradingview", "not-a-mapping", NOW)
        with self.assertRaises(QuarantineError):
            evaluate_submission("tradingview", _payload(), "not-an-int")


class DigestTests(unittest.TestCase):
    def test_identical_content_digests_identically(self):
        self.assertEqual(content_digest(_payload()), content_digest(_payload()))

    def test_key_order_does_not_change_the_digest(self):
        a = {"alpha": 1, "beta": 2}
        b = {"beta": 2, "alpha": 1}
        self.assertEqual(content_digest(a), content_digest(b))

    def test_changed_content_changes_the_digest(self):
        self.assertNotEqual(
            content_digest(_payload()), content_digest(_payload(price=1))
        )


class PromotionTests(unittest.TestCase):
    def test_nothing_self_promotes(self):
        blockers = promotion_blockers(True, reviewed_by=None, target_provenance="derived")
        self.assertIn("operator_review_required", [b["code"] for b in blockers])

    def test_a_rejected_submission_can_never_be_promoted(self):
        blockers = promotion_blockers(False, reviewed_by="chase", target_provenance="derived")
        self.assertIn("never_accepted", [b["code"] for b in blockers])

    def test_context_only_provenance_cannot_reach_a_directional_score(self):
        for provenance in ("proxy", "context_only", "unavailable"):
            with self.subTest(provenance=provenance):
                blockers = promotion_blockers(True, "chase", provenance)
                self.assertIn(
                    "provenance_not_scoreable", [b["code"] for b in blockers]
                )

    def test_a_reviewed_scoreable_item_has_no_blockers(self):
        self.assertEqual(promotion_blockers(True, "chase", "observed"), [])


if __name__ == "__main__":
    unittest.main()
