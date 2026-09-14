"""Operator drawings on the Market Canvas, validated and versioned.

A drawing is the operator's own reasoning made durable: a level they think
matters, a trendline they are watching, a note about why. The roadmap requires
these to be **versioned and stored server-side**, so that a paper trade can be
reconstructed from source observation through outcome without screenshots or
memory.

Versioning is the point. An edit supersedes rather than overwrites, because
"what did I think at the time" is a different question from "what do I think
now", and only the second survives an overwrite.

A drawing is annotation. It carries no scoring, approval or execution authority,
and nothing here can influence a signal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from tradesync_core.canvas_drawing_style import DrawingStyle, StyleError, validate_style

SCHEMA_VERSION = "canvas_drawing_v1"

MAX_LABEL_LENGTH = 280
# A freehand stroke is simplified in the browser before it is sent, to at most
# this many points. No other kind comes near it.
MAX_POINTS = 400

# Each kind declares how many anchor points it accepts, as (fewest, most).
# Validating the count here keeps a malformed shape out of storage rather than
# out of the renderer.
DRAWING_KINDS: dict[str, tuple[int, int]] = {
    "horizontal": (1, 1),       # a price level; time is ignored
    "horizontal_ray": (1, 1),   # a price level from its anchor to the right
    "vertical": (1, 1),         # a moment; price is ignored
    "trendline": (2, 2),        # a segment between two anchors
    "ray": (2, 2),              # from the first anchor through the second, onwards
    "extended_line": (2, 2),    # through both anchors, both ways
    "range": (2, 2),            # a rectangle between two anchors
    "rectangle": (2, 2),        # a rectangle between opposite corners
    "fib_retracement": (2, 2),  # retracement levels from a move's start to its end
    "pencil": (2, MAX_POINTS),  # a freehand stroke
    "note": (1, 1),             # a comment anchored at a point
    "text": (1, 1),             # text written on the chart at a point
}

# Kinds whose label is their content, so an empty label records nothing.
LABELLED_KINDS = frozenset({"note", "text"})


class DrawingError(ValueError):
    """Raised for a malformed drawing, never for an ordinary absence."""


@dataclass(frozen=True)
class DrawingPoint:
    """One anchor. ``time_s`` is UNIX seconds, matching the chart."""

    time_s: int
    price: float

    def to_dict(self) -> dict[str, Any]:
        return {"time_s": self.time_s, "price": self.price}


@dataclass(frozen=True)
class Drawing:
    symbol: str
    interval: str
    kind: str
    points: list[DrawingPoint]
    label: str = ""
    colour: str = ""
    points_raw: list[dict[str, Any]] = field(default_factory=list)
    style: DrawingStyle | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "symbol": self.symbol,
            "interval": self.interval,
            "kind": self.kind,
            "points": [p.to_dict() for p in self.points],
            "label": self.label,
            "colour": self.colour,
            "style": self.style.to_dict() if self.style else None,
            # Restated so no consumer mistakes an annotation for evidence.
            "authority": "none",
        }


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if number == number and abs(number) != float("inf") else None


def _check_point_count(kind: str, count: int) -> None:
    fewest, most = DRAWING_KINDS[kind]
    if fewest == most and count != fewest:
        raise DrawingError(f"a {kind} needs exactly {fewest} point(s), got {count}")
    if not fewest <= count <= most:
        raise DrawingError(f"a {kind} needs {fewest} to {most} points, got {count}")


def validate_drawing(payload: Mapping[str, Any]) -> Drawing:
    """Validate one drawing submission, or explain why it is malformed."""

    if not isinstance(payload, Mapping):
        raise DrawingError("drawing must be an object")

    kind = str(payload.get("kind", "")).strip()
    if kind not in DRAWING_KINDS:
        raise DrawingError(
            f"unknown drawing kind '{kind}'; expected one of "
            + ", ".join(sorted(DRAWING_KINDS))
        )

    symbol = str(payload.get("symbol", "")).strip()
    interval = str(payload.get("interval", "")).strip()
    if not symbol or not interval:
        raise DrawingError("symbol and interval are required")

    raw_points = payload.get("points")
    if not isinstance(raw_points, Sequence) or isinstance(raw_points, (str, bytes)):
        raise DrawingError("points must be a list")
    if len(raw_points) > MAX_POINTS:
        raise DrawingError(f"at most {MAX_POINTS} points are accepted")
    _check_point_count(kind, len(raw_points))

    points: list[DrawingPoint] = []
    for index, item in enumerate(raw_points):
        if not isinstance(item, Mapping):
            raise DrawingError(f"point {index} must be an object")
        price = _number(item.get("price"))
        time_s = item.get("time_s")
        if price is None or price <= 0:
            raise DrawingError(f"point {index} needs a positive finite price")
        if not isinstance(time_s, int) or isinstance(time_s, bool) or time_s <= 0:
            raise DrawingError(f"point {index} needs a positive integer time_s")
        points.append(DrawingPoint(time_s=time_s, price=price))

    # Anchors that all coincide make a degenerate shape: it renders as nothing
    # and usually means a click was registered twice.
    if len(points) >= 2 and len({(p.time_s, p.price) for p in points}) == 1:
        wanted = "two" if DRAWING_KINDS[kind][1] == 2 else "at least two"
        raise DrawingError(f"a {kind} needs {wanted} distinct points")

    label = str(payload.get("label", "")).strip()
    if len(label) > MAX_LABEL_LENGTH:
        raise DrawingError(f"label exceeds {MAX_LABEL_LENGTH} characters")
    if kind in LABELLED_KINDS and not label:
        raise DrawingError(f"a {kind} needs a label; an empty {kind} records nothing")

    try:
        style = validate_style(payload.get("style"))
    except StyleError as exc:
        raise DrawingError(str(exc)) from exc

    return Drawing(
        symbol=symbol,
        interval=interval,
        kind=kind,
        points=points,
        label=label,
        colour=str(payload.get("colour", "")).strip()[:32],
        style=style,
    )


def next_version(current_version: int | None) -> int:
    """Versions start at 1 and only ever increase."""
    if current_version is None:
        return 1
    if not isinstance(current_version, int) or isinstance(current_version, bool):
        raise DrawingError("version must be an integer")
    if current_version < 1:
        raise DrawingError("version must be positive")
    return current_version + 1
