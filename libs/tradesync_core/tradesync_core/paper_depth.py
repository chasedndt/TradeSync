"""Fill prices walked through an observed order book for a paper position's own size.

Slippage is measured from the book rather than assumed: an entry takes displayed
levels outward from the touch until its notional is filled, an exit takes levels
until its quantity is filled. Each walk keeps the levels it took and the snapshot
they came from, so the fill can be recomputed later from the stored book.

Costs are reported apart and are already inside the fill price; profit and loss
never deducts them a second time:

- half spread: from the mid to the touch;
- depth: past the touch;
- total: the average fill against the mid.

Displayed orders can be cancelled before an order arrives, so a walk is the cost
the book showed at that moment, not a guaranteed execution. A book aggregated to a
few significant figures quotes bucket edges and overstates the cost; every walk
records its snapshot's precision.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

MODEL = "observed_depth_walk_v1"


class InsufficientDepth(ValueError):
    """The displayed levels cannot fill the requested size."""


def _positive(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        return None
    return float(value)


def _level(row: Any) -> tuple[float | None, float | None]:
    if isinstance(row, Mapping):
        return _positive(row.get("price")), _positive(row.get("size"))
    if isinstance(row, (list, tuple)) and len(row) >= 2:
        return _positive(row[0]), _positive(row[1])
    return None, None


def levels(book: Mapping[str, Any], side: str) -> list[tuple[float, float]]:
    """(price, size) outward from the touch on the side an order takes: asks for a buy, bids for a sell."""
    if side not in ("buy", "sell"):
        raise ValueError("side must be buy or sell")
    key = "asks" if side == "buy" else "bids"
    rows = book.get(key)
    if not isinstance(rows, list) or not rows:
        raise InsufficientDepth(f"no displayed {key}")
    out: list[tuple[float, float]] = []
    for row in rows:
        price, size = _level(row)
        if price is None or size is None:
            raise ValueError("Book level without a finite positive price and size")
        if out and (price <= out[-1][0] if side == "buy" else price >= out[-1][0]):
            raise ValueError("Book levels are not ordered outward from the touch")
        out.append((price, size))
    return out


def _first_price(book: Mapping[str, Any], key: str) -> float | None:
    rows = book.get(key)
    return _level(rows[0])[0] if isinstance(rows, list) and rows else None


def snapshot(book: Mapping[str, Any], *, observed_at: float | None, received_at: float | None,
             source: str = "hyperliquid_l2_book", precision: str = "full") -> dict[str, Any]:
    """Where a walk's levels came from: source, precision, times and the touch on each side."""
    bids, asks = book.get("bids"), book.get("asks")
    return {"source": source, "precision": precision, "observed_at": observed_at, "received_at": received_at,
            "best_bid": _first_price(book, "bids"), "best_ask": _first_price(book, "asks"),
            "bid_levels": len(bids) if isinstance(bids, list) else 0, "ask_levels": len(asks) if isinstance(asks, list) else 0}


def walk(book: Mapping[str, Any], side: str, *, notional: float | None = None, quantity: float | None = None,
         source: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Take levels until ``notional`` (quote currency) or ``quantity`` (base units) is filled."""
    if (notional is None) == (quantity is None):
        raise ValueError("A walk needs exactly one of notional or quantity")
    by_notional = notional is not None
    goal = _positive(notional if by_notional else quantity)
    if goal is None:
        raise ValueError("Walk size must be finite and positive")
    ladder = levels(book, side)
    tolerance = goal * 1e-12
    taken: list[list[float]] = []
    cost = filled = 0.0
    for price, size in ladder:
        remaining = goal - (cost if by_notional else filled)
        if remaining <= tolerance:
            break
        take = min(size, remaining / price if by_notional else remaining)
        taken.append([price, take])
        cost += take * price
        filled += take
    if goal - (cost if by_notional else filled) > tolerance:
        share = (cost if by_notional else filled) / goal
        raise InsufficientDepth(f"displayed depth fills {share:.1%} of the size across {len(ladder)} levels")
    sign = 1 if side == "buy" else -1
    average = cost / filled
    touch = ladder[0][0]
    bid, ask = _first_price(book, "bids"), _first_price(book, "asks")
    mid = (bid + ask) / 2 if bid and ask else None
    return {
        "model": MODEL, "side": side, "price": average, "quantity": filled, "notional_usdc": cost,
        "touch": touch, "mid": mid, "levels_taken": taken, "levels_available": len(ladder),
        "half_spread_bps": sign * (touch - mid) / mid * 10_000 + 0.0 if mid else None,
        "depth_bps": sign * (average - touch) / touch * 10_000 + 0.0,
        "total_bps": sign * (average - mid) / mid * 10_000 + 0.0 if mid else None,
        "total_usdc": sign * (average - mid) * filled + 0.0 if mid else None,
        "snapshot": dict(source) if source is not None else None,
    }


def priced(reference_price: float, walked: Mapping[str, Any]) -> float:
    """``reference_price`` moved against the order by a walk's total cost against its book's mid."""
    reference = _positive(reference_price)
    if reference is None:
        raise ValueError("Reference price must be finite and positive")
    if walked.get("total_bps") is None:
        raise ValueError("Book has no mid; its cost against the mid is unknown")
    sign = 1 if walked["side"] == "buy" else -1
    return reference * (1 + sign * walked["total_bps"] / 10_000)


def book_fill(walked: Mapping[str, Any]) -> dict[str, Any]:
    """A fill at a walk's own average price: the live path, where the walked book is the observation."""
    return {**walked, "basis": "book_walk", "fill_price": walked["price"], "reference_price": walked["touch"],
            "cost_bps": walked["total_bps"], "cost_usdc": walked["total_usdc"]}


def reference_fill(walked: Mapping[str, Any], reference_price: float, quantity: float) -> dict[str, Any]:
    """A fill at ``reference_price`` moved by a recorded book's cost against its mid: candles and replays."""
    price = priced(reference_price, walked)
    return {"basis": "reference_moved_by_book_cost", "fill_price": price, "quantity": quantity,
            "reference_price": reference_price, "cost_bps": walked["total_bps"],
            "cost_usdc": abs(price - reference_price) * quantity, "half_spread_bps": walked["half_spread_bps"],
            "depth_bps": walked["depth_bps"], "total_bps": walked["total_bps"], "snapshot": walked["snapshot"],
            "walk": dict(walked)}
