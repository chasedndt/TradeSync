"""How a canvas drawing is drawn: its colour, line width, and whether it is dashed.

The style is stored with each version so a chart replayed later looks the way
it did when the operator drew it. It is presentation only. Nothing reads it
except the canvas, and it can never change what a drawing means.

A style is optional as a whole (drawings made before styles existed have
none), but a style that is sent is complete: a half-specified style would
leave the renderer to guess the rest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

STYLE_FIELDS = ("colour", "width", "dashed")
MIN_WIDTH = 1
MAX_WIDTH = 4
_COLOUR = re.compile(r"#[0-9a-fA-F]{6}")


class StyleError(ValueError):
    """Raised for a malformed style."""


@dataclass(frozen=True)
class DrawingStyle:
    colour: str
    width: int
    dashed: bool

    def to_dict(self) -> dict[str, Any]:
        return {"colour": self.colour, "width": self.width, "dashed": self.dashed}


def validate_style(raw: Any) -> DrawingStyle | None:
    """Validate an optional style. ``None`` means no style was recorded."""

    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise StyleError("style must be an object")

    unknown = sorted(str(name) for name in raw if name not in STYLE_FIELDS)
    if unknown:
        raise StyleError("style has unknown field(s): " + ", ".join(unknown))
    missing = [name for name in STYLE_FIELDS if name not in raw]
    if missing:
        raise StyleError("style needs " + ", ".join(missing))

    colour = raw["colour"]
    if not isinstance(colour, str) or not _COLOUR.fullmatch(colour):
        raise StyleError("style colour must be #rrggbb")

    width = raw["width"]
    # bool is an int in Python; a width of True is a mistake, not a 1.
    if isinstance(width, bool) or not isinstance(width, int) or not MIN_WIDTH <= width <= MAX_WIDTH:
        raise StyleError(f"style width must be a whole number from {MIN_WIDTH} to {MAX_WIDTH}")

    dashed = raw["dashed"]
    if not isinstance(dashed, bool):
        raise StyleError("style dashed must be true or false")

    return DrawingStyle(colour=colour.lower(), width=width, dashed=dashed)
