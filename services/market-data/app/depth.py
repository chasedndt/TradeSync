"""Order book shape for the Market Canvas.

Depth is not a time series. The book is a photograph of resting intent right
now, and it is replaced wholesale on every poll — there is no honest way to draw
it as an overlay across past candles, so the canvas shows it beside the chart
instead, with the one thing that *can* be drawn on the price axis: the levels
where size is actually sitting.

These are pure functions over an already-parsed book so the arithmetic can be
tested without a venue.

A wall here is a description, never a prediction. Resting size can be pulled the
instant it is approached, so nothing in this module may reach the feature
catalog or a paper signal.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

# A level must hold at least this share of its side's visible notional before it
# is worth drawing on the price axis. Below it, "the biggest level" is just the
# ordinary lumpiness of a book and marking it would be noise dressed as signal.
WALL_MIN_SHARE = 0.15


def cumulative_ladder(
    levels: Sequence[Mapping[str, Any]],
) -> list[dict[str, float]]:
    """Running notional outward from the touch.

    Level notional is price × size. The cumulative column answers "how much
    would it cost to sweep to here", which is the question a depth chart is
    actually being asked.
    """
    out: list[dict[str, float]] = []
    running = 0.0
    for level in levels:
        try:
            price = float(level["price"])
            size = float(level["size"])
        except (KeyError, TypeError, ValueError):
            continue
        notional = price * size
        running += notional
        out.append(
            {
                "price": price,
                "size": size,
                "notional_usd": notional,
                "cumulative_usd": running,
                "orders": int(level.get("orders", 0) or 0),
            }
        )
    return out


def resting_walls(
    bids: Sequence[Mapping[str, Any]],
    asks: Sequence[Mapping[str, Any]],
    *,
    min_share: float = WALL_MIN_SHARE,
    limit: int = 2,
) -> list[dict[str, Any]]:
    """Levels holding an outsized share of their side's visible notional.

    Share is measured against the side's own total, not against both sides
    combined, so a thin ask book cannot promote an ordinary bid into a wall.

    Returns at most ``limit`` per side, largest first. An empty list is the
    normal answer for an evenly distributed book and must be shown as such
    rather than by lowering the threshold until something appears.
    """
    walls: list[dict[str, Any]] = []
    for side, levels in (("bid", bids), ("ask", asks)):
        ladder = cumulative_ladder(levels)
        total = sum(level["notional_usd"] for level in ladder)
        if total <= 0:
            continue
        ranked = sorted(ladder, key=lambda level: level["notional_usd"], reverse=True)
        for level in ranked[:limit]:
            share = level["notional_usd"] / total
            if share < min_share:
                break
            walls.append(
                {
                    "side": side,
                    "price": level["price"],
                    "notional_usd": round(level["notional_usd"], 2),
                    "share_of_side": round(share, 4),
                }
            )
    return walls


def summarise_book(book: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The canvas-facing view of one order book poll.

    Returns ``None`` for a missing book rather than an empty ladder, so the UI
    can say the venue did not answer instead of drawing an empty market.
    """
    if not book:
        return None

    bids = book.get("bids") or []
    asks = book.get("asks") or []
    return {
        "venue": book.get("venue"),
        "symbol": book.get("symbol"),
        "poll_ts": book.get("poll_ts"),
        "best_bid": book.get("best_bid"),
        "best_ask": book.get("best_ask"),
        "mid_price": book.get("mid_price"),
        "spread_bps": book.get("spread_bps"),
        "imbalance_1pct": book.get("imbalance_1pct"),
        "depth": book.get("depth"),
        "bids": cumulative_ladder(bids),
        "asks": cumulative_ladder(asks),
        "walls": resting_walls(bids, asks),
        # Restated on the response because this is the surface most likely to be
        # mistaken for a trading signal.
        "authority": "display_only",
    }
