"""Canvas drawing validation tests.

A drawing is the operator's own reasoning made durable. The validator's job is
to keep malformed shapes out of storage rather than out of the renderer, so the
refusals are what matter here.
"""

import unittest

from tradesync_core.canvas_drawings import (
    MAX_LABEL_LENGTH,
    DrawingError,
    next_version,
    validate_drawing,
)

T = 1_788_800_000


def _payload(kind="horizontal", points=None, **extra):
    base = {
        "symbol": "BTC-PERP",
        "interval": "15m",
        "kind": kind,
        "points": points if points is not None else [{"time_s": T, "price": 79000.0}],
    }
    base.update(extra)
    return base


class KindTests(unittest.TestCase):
    def test_a_horizontal_takes_one_point(self):
        drawing = validate_drawing(_payload())
        self.assertEqual(drawing.kind, "horizontal")
        self.assertEqual(len(drawing.points), 1)
        self.assertEqual(drawing.points[0].price, 79000.0)

    def test_a_trendline_takes_two(self):
        drawing = validate_drawing(_payload("trendline", [
            {"time_s": T, "price": 79000.0},
            {"time_s": T + 3600, "price": 79500.0},
        ]))
        self.assertEqual(len(drawing.points), 2)

    def test_the_wrong_point_count_is_refused_with_the_expected_number(self):
        with self.assertRaisesRegex(DrawingError, "exactly 2"):
            validate_drawing(_payload("trendline"))

    def test_an_unknown_kind_lists_the_valid_ones(self):
        with self.assertRaisesRegex(DrawingError, "trendline"):
            validate_drawing(_payload("scribble"))

    def test_two_identical_anchors_are_refused(self):
        """A degenerate shape renders as nothing; usually a double click."""
        same = {"time_s": T, "price": 79000.0}
        with self.assertRaisesRegex(DrawingError, "distinct"):
            validate_drawing(_payload("trendline", [same, dict(same)]))


class PointTests(unittest.TestCase):
    def test_a_non_positive_price_is_refused(self):
        with self.assertRaisesRegex(DrawingError, "positive finite price"):
            validate_drawing(_payload(points=[{"time_s": T, "price": 0}]))

    def test_a_non_finite_price_is_refused(self):
        with self.assertRaises(DrawingError):
            validate_drawing(_payload(points=[{"time_s": T, "price": float("inf")}]))

    def test_a_missing_or_bad_time_is_refused(self):
        with self.assertRaisesRegex(DrawingError, "time_s"):
            validate_drawing(_payload(points=[{"price": 79000.0}]))
        with self.assertRaisesRegex(DrawingError, "time_s"):
            validate_drawing(_payload(points=[{"time_s": "yesterday", "price": 79000.0}]))

    def test_a_boolean_is_not_a_number(self):
        with self.assertRaises(DrawingError):
            validate_drawing(_payload(points=[{"time_s": True, "price": 79000.0}]))

    def test_points_must_be_a_list_of_objects(self):
        with self.assertRaisesRegex(DrawingError, "points must be a list"):
            validate_drawing(_payload(points="79000"))
        with self.assertRaisesRegex(DrawingError, "must be an object"):
            validate_drawing(_payload(points=["79000"]))


class LabelTests(unittest.TestCase):
    def test_a_note_without_a_label_records_nothing_and_is_refused(self):
        with self.assertRaisesRegex(DrawingError, "needs a label"):
            validate_drawing(_payload("note", label=""))

    def test_a_note_with_a_label_is_accepted(self):
        drawing = validate_drawing(_payload("note", label="watching this sweep"))
        self.assertEqual(drawing.label, "watching this sweep")

    def test_an_overlong_label_is_refused(self):
        with self.assertRaisesRegex(DrawingError, "exceeds"):
            validate_drawing(_payload(label="x" * (MAX_LABEL_LENGTH + 1)))


class ContextTests(unittest.TestCase):
    def test_symbol_and_interval_are_required(self):
        payload = _payload()
        payload["symbol"] = ""
        with self.assertRaisesRegex(DrawingError, "symbol and interval"):
            validate_drawing(payload)

    def test_a_drawing_claims_no_authority(self):
        """An annotation must never read as evidence."""
        self.assertEqual(validate_drawing(_payload()).to_dict()["authority"], "none")


class VersionTests(unittest.TestCase):
    def test_versions_start_at_one(self):
        self.assertEqual(next_version(None), 1)

    def test_versions_only_increase(self):
        self.assertEqual(next_version(1), 2)
        self.assertEqual(next_version(7), 8)

    def test_a_non_positive_or_non_integer_version_is_refused(self):
        with self.assertRaises(DrawingError):
            next_version(0)
        with self.assertRaises(DrawingError):
            next_version("2")


if __name__ == "__main__":
    unittest.main()
