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

SCHEMA_VERSION = "canvas_drawing_v1"

# Each kind declares how many anchor points it needs. Validating the count here
# keeps a malformed shape out of storage rather than out of the renderer.
DRAWING_KINDS: dict[str, int] = {
    "horizontal": 1,   # a price level; time is ignored
    "trendline": 2,    # two anchors
    "range": 2,        # a rectangle between two anchors
    "note": 1,         # a comment anchored at a point
}

MAX_LABEL_LENGTH = 280
MAX_POINTS = 8


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "symbol": self.symbol,
            "interval": self.interval,
            "kind": self.kind,
            "points": [p.to_dict() for p in self.points],
            "label": self.label,
            "colour": self.colour,
            # Restated so no consumer mistakes an annotation for evidence.
            "authority": "none",
        }


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if number == number and abs(number) != float("inf") else None


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

    expected = DRAWING_KINDS[kind]
    if len(raw_points) != expected:
        raise DrawingError(
            f"a {kind} needs exactly {expected} point(s), got {len(raw_points)}"
        )

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

    # A two-anchor shape with identical anchors is degenerate: it renders as
    # nothing and usually means a click was registered twice.
    if expected == 2 and points[0].time_s == points[1].time_s and points[0].price == points[1].price:
        raise DrawingError(f"a {kind} needs two distinct points")

    label = str(payload.get("label", "")).strip()
    if len(label) > MAX_LABEL_LENGTH:
        raise DrawingError(f"label exceeds {MAX_LABEL_LENGTH} characters")
    if kind == "note" and not label:
        raise DrawingError("a note needs a label; an empty note records nothing")

    return Drawing(
        symbol=symbol,
        interval=interval,
        kind=kind,
        points=points,
        label=label,
        colour=str(payload.get("colour", "")).strip()[:32],
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
