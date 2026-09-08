"""State ageing and flap-detection tests.

A state without a duration is half a fact: "offline" reads the same whether it
happened ten seconds ago or yesterday. These tests pin the difference.
"""

import unittest

from tradesync_core.state_history import (
    annotate_node,
    count_flaps,
    describe_duration,
    detect_transitions,
    is_flapping,
)

NOW = 1_788_800_000


class DetectTransitionsTests(unittest.TestCase):
    def test_unchanged_states_produce_no_transition(self):
        observed = {"market_data": "live", "scorer_fusion": "offline"}
        self.assertEqual(detect_transitions(observed, dict(observed), NOW), [])

    def test_a_changed_state_is_reported_with_both_sides(self):
        [t] = detect_transitions(
            {"scorer_fusion": "live"}, {"scorer_fusion": "offline"}, NOW
        )
        self.assertEqual(t.node_id, "scorer_fusion")
        self.assertEqual(t.previous_state, "offline")
        self.assertEqual(t.new_state, "live")
        self.assertEqual(t.at_epoch_s, NOW)

    def test_a_first_sighting_starts_history_rather_than_assuming_forever(self):
        [t] = detect_transitions({"new_node": "live"}, {}, NOW)
        self.assertIsNone(t.previous_state)
        self.assertEqual(t.new_state, "live")

    def test_transitions_are_ordered_for_a_stable_record(self):
        transitions = detect_transitions(
            {"zulu": "live", "alpha": "offline"}, {}, NOW
        )
        self.assertEqual([t.node_id for t in transitions], ["alpha", "zulu"])

    def test_a_node_that_disappeared_is_not_invented_as_a_transition(self):
        self.assertEqual(detect_transitions({}, {"gone": "live"}, NOW), [])


class DescribeDurationTests(unittest.TestCase):
    def test_coarse_phrasing_by_magnitude(self):
        self.assertEqual(describe_duration(45), "45s")
        self.assertEqual(describe_duration(600), "10m")
        self.assertEqual(describe_duration(3600), "1h")
        self.assertEqual(describe_duration(3600 + 1800), "1h 30m")
        self.assertEqual(describe_duration(86400 * 2), "2d")
        self.assertEqual(describe_duration(86400 * 2 + 3600 * 5), "2d 5h")

    def test_unknown_and_negative_are_handled(self):
        self.assertEqual(describe_duration(None), "unknown")
        self.assertEqual(describe_duration(-10), "0s")


class FlapTests(unittest.TestCase):
    def _transitions(self, count, spacing=60):
        return [{"at_epoch_s": NOW - i * spacing} for i in range(count)]

    def test_transitions_inside_the_window_are_counted(self):
        self.assertEqual(count_flaps(self._transitions(3), NOW), 3)

    def test_transitions_outside_the_window_are_not(self):
        old = [{"at_epoch_s": NOW - 5000}, {"at_epoch_s": NOW - 60}]
        self.assertEqual(count_flaps(old, NOW), 1)

    def test_a_settled_stage_is_not_flapping(self):
        self.assertFalse(is_flapping(self._transitions(2), NOW))

    def test_an_oscillating_stage_is_flagged(self):
        """Four changes in fifteen minutes is oscillation, not transition."""
        self.assertTrue(is_flapping(self._transitions(4), NOW))

    def test_malformed_entries_do_not_break_counting(self):
        entries = ["nope", {"at_epoch_s": "bad"}, {}, {"at_epoch_s": NOW - 30}]
        self.assertEqual(count_flaps(entries, NOW), 1)


class AnnotateNodeTests(unittest.TestCase):
    def test_duration_and_phrasing_are_attached(self):
        node = annotate_node(
            {"id": "scorer_fusion", "status": "offline"},
            entered_at_epoch_s=NOW - 7200,
            now_epoch_s=NOW,
        )
        self.assertEqual(node["state_duration_seconds"], 7200)
        self.assertEqual(node["state_age"], "2h")
        self.assertEqual(node["status"], "offline")

    def test_unknown_history_says_so_rather_than_implying_freshness(self):
        node = annotate_node(
            {"id": "x", "status": "live"}, entered_at_epoch_s=None, now_epoch_s=NOW
        )
        self.assertIsNone(node["state_duration_seconds"])
        self.assertEqual(node["state_age"], "unknown")

    def test_the_original_node_is_not_mutated(self):
        original = {"id": "x", "status": "live"}
        annotate_node(original, NOW - 10, NOW)
        self.assertNotIn("state_age", original)

    def test_flapping_is_surfaced_on_the_node(self):
        node = annotate_node(
            {"id": "x", "status": "live"},
            entered_at_epoch_s=NOW - 30,
            now_epoch_s=NOW,
            recent_transitions=[{"at_epoch_s": NOW - i * 60} for i in range(5)],
        )
        self.assertTrue(node["flapping"])
        self.assertEqual(node["recent_transitions"], 5)


if __name__ == "__main__":
    unittest.main()
