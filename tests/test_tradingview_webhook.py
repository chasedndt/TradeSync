"""TradingView webhook parsing and authentication tests.

This is the code an unauthenticated internet endpoint would run. Its refusals
matter more than its acceptances, so they are asserted individually.
"""

import json
import unittest

from tradesync_core.tradingview_webhook import (
    MAX_BODY_BYTES,
    TRADINGVIEW_SOURCE_IPS,
    WebhookError,
    is_allowed_source,
    parse_alert,
)

SECRET = "correct-horse-battery-staple"


def _body(**overrides):
    payload = {
        "secret": SECRET,
        "indicator": "StrikeZone FVG Engine",
        "ticker": "BTCUSD",
        "interval": "15m",
        "action": "buy",
        "price": 79000,
    }
    payload.update(overrides)
    return json.dumps(payload)


class AuthenticationTests(unittest.TestCase):
    def test_a_correct_secret_authenticates(self):
        alert = parse_alert(_body(), SECRET)
        self.assertTrue(alert.authenticated)
        self.assertEqual(alert.reasons, [])
        self.assertEqual(alert.indicator, "StrikeZone FVG Engine")

    def test_a_wrong_secret_is_refused_not_raised(self):
        """A wrong secret is ordinary traffic on a public endpoint."""
        alert = parse_alert(_body(secret="guess"), SECRET)
        self.assertFalse(alert.authenticated)
        self.assertIn("bad_secret", [r["code"] for r in alert.reasons])

    def test_a_missing_secret_is_refused(self):
        payload = json.loads(_body())
        del payload["secret"]
        alert = parse_alert(json.dumps(payload), SECRET)
        self.assertFalse(alert.authenticated)

    def test_the_secret_never_travels_into_storage(self):
        alert = parse_alert(_body(), SECRET)
        self.assertNotIn("secret", alert.payload)
        self.assertNotIn("secret", json.dumps(alert.to_submission()))

    def test_refusing_to_run_without_a_configured_secret(self):
        """An unauthenticated public endpoint is not an acceptable default."""
        with self.assertRaises(WebhookError):
            parse_alert(_body(), "")


class BodyValidationTests(unittest.TestCase):
    def test_plain_text_cannot_be_authenticated(self):
        alert = parse_alert("BUY BTCUSD now", SECRET)
        self.assertFalse(alert.authenticated)
        self.assertIn("body_not_json", [r["code"] for r in alert.reasons])

    def test_a_json_array_is_refused(self):
        alert = parse_alert("[1,2,3]", SECRET)
        self.assertIn("body_not_object", [r["code"] for r in alert.reasons])

    def test_an_oversized_body_is_refused_before_parsing(self):
        alert = parse_alert(b"x" * (MAX_BODY_BYTES + 1), SECRET)
        self.assertIn("body_too_large", [r["code"] for r in alert.reasons])

    def test_invalid_utf8_is_refused(self):
        alert = parse_alert(b"\xff\xfe\x00bad", SECRET)
        self.assertIn("body_not_utf8", [r["code"] for r in alert.reasons])

    def test_each_alert_must_identify_itself(self):
        """One endpoint serves many alerts, so the body carries the routing."""
        alert = parse_alert(_body(indicator="", ticker=""), SECRET)
        self.assertFalse(alert.authenticated)
        reason = next(r for r in alert.reasons if r["code"] == "missing_fields")
        self.assertIn("indicator", reason["detail"])
        self.assertIn("ticker", reason["detail"])

    def test_bytes_and_str_bodies_behave_identically(self):
        self.assertTrue(parse_alert(_body().encode("utf-8"), SECRET).authenticated)


class SubmissionTests(unittest.TestCase):
    def test_the_submission_carries_routing_and_the_original_alert(self):
        submission = parse_alert(_body(), SECRET).to_submission()
        self.assertEqual(submission["indicator"], "StrikeZone FVG Engine")
        self.assertEqual(submission["ticker"], "BTCUSD")
        self.assertEqual(submission["interval"], "15m")
        self.assertEqual(submission["alert"]["price"], 79000)

    def test_the_submission_claims_no_authority(self):
        """It must survive quarantine's forbidden-field check."""
        from tradesync_core.quarantine import FORBIDDEN_FIELDS

        submission = parse_alert(_body(), SECRET).to_submission()
        self.assertEqual(FORBIDDEN_FIELDS.intersection(submission.keys()), set())

    def test_an_alert_cannot_smuggle_authority_through(self):
        alert = parse_alert(_body(admitted=True, scoring_allowed=True), SECRET)
        submission = alert.to_submission()
        # It parses, but quarantine refuses it by name at the next boundary.
        from tradesync_core.quarantine import evaluate_submission

        verdict = evaluate_submission("tradingview", submission["alert"], 1_788_800_000_000)
        self.assertFalse(verdict.accepted)
        self.assertIn(
            "payload_claims_authority", [r["code"] for r in verdict.reasons]
        )


class SourceTests(unittest.TestCase):
    def test_published_addresses_are_recognised(self):
        for ip in TRADINGVIEW_SOURCE_IPS:
            self.assertTrue(is_allowed_source(ip))

    def test_anything_else_is_not(self):
        self.assertFalse(is_allowed_source("203.0.113.7"))
        self.assertFalse(is_allowed_source(""))


if __name__ == "__main__":
    unittest.main()


def test_the_waf_allowlist_and_the_receiver_name_the_same_four_ips() -> None:
    """One fact recorded in two places must not drift apart.

    The Cloudflare edge rule and the receiver's own check are independent
    layers, deliberately — the edge can be misconfigured or disabled, and the
    receiver's check costs nothing. But they have to agree about *which*
    addresses, or the edge silently blocks traffic the receiver would accept, or
    worse, admits traffic the receiver then rejects for a reason nobody can see
    at the edge.

    If TradingView changes its egress addresses, both move together or this
    fails.
    """
    import re
    from pathlib import Path

    runbook = (
        Path(__file__).resolve().parents[1] / "ops" / "ingress" / "waf-allowlist.md"
    ).read_text(encoding="utf-8")

    # The addresses inside the expression block, not every IP-shaped string in
    # the prose.
    expression = runbook.split("ip.src in {", 1)[1].split("}", 1)[0]
    documented = set(re.findall(r"\d+\.\d+\.\d+\.\d+", expression))

    assert documented == set(TRADINGVIEW_SOURCE_IPS), (
        "ops/ingress/waf-allowlist.md and TRADINGVIEW_SOURCE_IPS disagree: "
        f"doc has {sorted(documented)}, code has {sorted(TRADINGVIEW_SOURCE_IPS)}"
    )
