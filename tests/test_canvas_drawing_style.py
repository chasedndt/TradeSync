"""Canvas drawing style validation.

A style is presentation only, but it is stored with every version, so a
malformed one is refused before it reaches storage like any other field.
"""

import unittest

from tradesync_core.canvas_drawing_style import (
    MAX_WIDTH,
    MIN_WIDTH,
    StyleError,
    validate_style,
)
from tradesync_core.canvas_drawings import DrawingError, validate_drawing

T = 1_788_800_000
STYLE = {"colour": "#E3B23C", "width": 2, "dashed": False}


def _style(**changes):
    style = dict(STYLE)
    style.update(changes)
    return style


def _drawing(**extra):
    payload = {
        "symbol": "BTC-PERP",
        "interval": "15m",
        "kind": "trendline",
        "points": [{"time_s": T, "price": 79000.0}, {"time_s": T + 900, "price": 79400.0}],
    }
    payload.update(extra)
    return payload


class StyleTests(unittest.TestCase):
    def test_no_style_means_none_was_recorded(self):
        self.assertIsNone(validate_style(None))

    def test_a_complete_style_is_accepted_with_its_colour_lowercased(self):
        style = validate_style(STYLE)
        self.assertEqual(style.to_dict(), {"colour": "#e3b23c", "width": 2, "dashed": False})

    def test_the_width_bounds_are_one_to_four_inclusive(self):
        self.assertEqual((MIN_WIDTH, MAX_WIDTH), (1, 4))
        for width in (1, 4):
            with self.subTest(width=width):
                self.assertEqual(validate_style(_style(width=width)).width, width)
        for width in (0, 5, -1):
            with self.subTest(width=width), self.assertRaisesRegex(StyleError, "width"):
                validate_style(_style(width=width))

    def test_a_width_must_be_a_whole_number_not_a_boolean_or_string(self):
        for width in (True, 2.0, "2", None):
            with self.subTest(width=width), self.assertRaisesRegex(StyleError, "width"):
                validate_style(_style(width=width))

    def test_a_colour_must_be_six_hex_digits_after_a_hash(self):
        for colour in ("#fff", "e3b23c", "#e3b23g", "red", "#e3b23c80", 0xE3B23C, None):
            with self.subTest(colour=colour), self.assertRaisesRegex(StyleError, "colour"):
                validate_style(_style(colour=colour))

    def test_dashed_must_be_a_boolean(self):
        for dashed in (0, 1, "false", None):
            with self.subTest(dashed=dashed), self.assertRaisesRegex(StyleError, "dashed"):
                validate_style(_style(dashed=dashed))

    def test_a_sent_style_is_complete(self):
        partial = {"colour": "#e3b23c", "width": 2}
        with self.assertRaisesRegex(StyleError, "needs dashed"):
            validate_style(partial)
        with self.assertRaisesRegex(StyleError, "needs"):
            validate_style({})

    def test_unknown_fields_are_refused_by_name(self):
        with self.assertRaisesRegex(StyleError, "opacity"):
            validate_style(_style(opacity=0.5))

    def test_a_style_must_be_an_object(self):
        for raw in ("dashed", ["#e3b23c", 2, False], 3):
            with self.subTest(raw=raw), self.assertRaisesRegex(StyleError, "object"):
                validate_style(raw)


class DrawingWithStyleTests(unittest.TestCase):
    def test_a_drawing_carries_its_validated_style(self):
        drawing = validate_drawing(_drawing(style=STYLE))
        self.assertEqual(drawing.to_dict()["style"], {"colour": "#e3b23c", "width": 2, "dashed": False})

    def test_a_drawing_without_a_style_records_none(self):
        self.assertIsNone(validate_drawing(_drawing()).to_dict()["style"])

    def test_a_malformed_style_refuses_the_drawing_as_a_drawing_error(self):
        with self.assertRaisesRegex(DrawingError, "width"):
            validate_drawing(_drawing(style=_style(width=9)))


if __name__ == "__main__":
    unittest.main()
