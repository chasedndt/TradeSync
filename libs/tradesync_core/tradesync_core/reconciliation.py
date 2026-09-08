"""Compare what this system believes it did against what actually happened.

Reconciliation is the part of an execution foundation that exists to **catch
divergence**, not to cause anything. It reads two records and reports where they
disagree. Nothing here can place, amend or cancel an order, and it works
identically in paper mode — which is the only mode this system runs in.

That distinction is the reason this is buildable while the rest of Slot 6 is
not. `EXECUTION_ENABLED=false` and gate 1.2 returned negative, so nothing argues
for building a signer or connecting a wallet. But a system that cannot tell you
when its own records have drifted apart is *less* safe, and the day that matters
is the day something did execute and the ledger disagrees.

Three divergence classes, and each one means something different:

- **orphan_decision** — a decision was approved and no order exists for it. Either
  execution never happened, or it happened and was not recorded. Those have
  opposite remedies, which is why the class does not guess between them.
- **orphan_order** — an order exists with no decision behind it. Nothing in this
  system should be able to produce one. If it appears, something wrote to the
  order table outside the decision path.
- **field_mismatch** — both exist and disagree about symbol, side, size or venue.
  The recorded intent and the recorded action are not the same trade.

A clean reconciliation is a positive result and is reported as one. "No
divergence found" is a fact worth stating, not silence.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

# Fields that must agree between a decision and the order that carried it out.
# Money and direction: the things where a mismatch is a different trade rather
# than a formatting difference.
RECONCILED_FIELDS = ("symbol", "side", "size_usd", "venue")

# Sizes are floats through JSON and a venue rounds to its own lot size. This is
# the point past which a difference is a discrepancy rather than rounding.
SIZE_TOLERANCE_USD = 0.01


class Divergence:
    """One disagreement, with enough to act on it."""

    __slots__ = ("kind", "decision_id", "order_id", "field", "expected", "actual", "detail")

    def __init__(
        self,
        kind: str,
        *,
        decision_id: str | None = None,
        order_id: str | None = None,
        field: str | None = None,
        expected: Any = None,
        actual: Any = None,
        detail: str = "",
    ):
        self.kind = kind
        self.decision_id = decision_id
        self.order_id = order_id
        self.field = field
        self.expected = expected
        self.actual = actual
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "decision_id": self.decision_id,
            "order_id": self.order_id,
            "field": self.field,
            "expected": self.expected,
            "actual": self.actual,
            "detail": self.detail,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Divergence({self.kind}, {self.decision_id}, {self.field})"


def reconcile(
    decisions: Iterable[Mapping[str, Any]],
    orders: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compare recorded decisions against recorded orders.

    ``decisions`` need ``id`` and a ``requested`` mapping; ``orders`` need
    ``decision_id`` and a ``request`` mapping. Both are what state-api already
    stores, so reconciliation reads the system's own records rather than a
    parallel bookkeeping nobody maintains.
    """
    by_decision: dict[str, Mapping[str, Any]] = {}
    duplicate_orders: list[Divergence] = []

    for order in orders:
        key = _text(order.get("decision_id"))
        if not key:
            duplicate_orders.append(
                Divergence(
                    "orphan_order",
                    order_id=_text(order.get("id")),
                    detail="order carries no decision_id; nothing in this system "
                    "should be able to produce one",
                )
            )
            continue
        if key in by_decision:
            # The unique constraint on decision_id should make this impossible.
            # If it appears, the constraint is gone or something wrote around it.
            duplicate_orders.append(
                Divergence(
                    "duplicate_order",
                    decision_id=key,
                    order_id=_text(order.get("id")),
                    detail="a second order exists for one decision; one approval "
                    "must not produce two orders",
                )
            )
            continue
        by_decision[key] = order

    divergences: list[Divergence] = list(duplicate_orders)
    matched = 0
    seen_decisions: set[str] = set()

    for decision in decisions:
        decision_id = _text(decision.get("id"))
        if not decision_id:
            continue
        seen_decisions.add(decision_id)
        order = by_decision.get(decision_id)

        if order is None:
            divergences.append(
                Divergence(
                    "orphan_decision",
                    decision_id=decision_id,
                    detail="a decision with no order. Either execution never "
                    "happened or it happened unrecorded; those have opposite "
                    "remedies, so this does not guess between them",
                )
            )
            continue

        matched += 1
        divergences.extend(_compare(decision_id, decision, order))

    # Orders whose decision is not in the window are not orphans — the window
    # simply did not reach back far enough. Saying otherwise would manufacture a
    # finding out of a query bound.
    unmatched_orders = sorted(set(by_decision) - seen_decisions)

    return {
        "decisions": len(seen_decisions),
        "orders": len(by_decision),
        "matched": matched,
        "divergences": [d.to_dict() for d in divergences],
        "orders_outside_window": unmatched_orders,
        "clean": not divergences,
        # Stated positively. "No divergence found" is a result, not silence.
        "summary": (
            f"{matched} of {len(seen_decisions)} decisions reconciled with no divergence"
            if not divergences
            else f"{len(divergences)} divergence(s) across {len(seen_decisions)} decisions"
        ),
    }


def _compare(
    decision_id: str, decision: Mapping[str, Any], order: Mapping[str, Any]
) -> list[Divergence]:
    """Field-by-field, on the things where a mismatch is a different trade."""
    requested = decision.get("requested") or {}
    placed = order.get("request") or {}
    if not isinstance(requested, Mapping) or not isinstance(placed, Mapping):
        return [
            Divergence(
                "field_mismatch",
                decision_id=decision_id,
                order_id=_text(order.get("id")),
                detail="decision or order payload is not a mapping",
            )
        ]

    out: list[Divergence] = []
    for field in RECONCILED_FIELDS:
        expected = requested.get(field)
        actual = placed.get(field)
        if expected is None and actual is None:
            continue
        if _equal(field, expected, actual):
            continue
        out.append(
            Divergence(
                "field_mismatch",
                decision_id=decision_id,
                order_id=_text(order.get("id")),
                field=field,
                expected=expected,
                actual=actual,
                detail=f"recorded intent and recorded action disagree on {field}",
            )
        )
    return out


def _equal(field: str, expected: Any, actual: Any) -> bool:
    if field == "size_usd":
        try:
            return abs(float(expected) - float(actual)) <= SIZE_TOLERANCE_USD
        except (TypeError, ValueError):
            return expected == actual
    if isinstance(expected, str) and isinstance(actual, str):
        # A venue may echo a side back in a different case. That is not a
        # different trade.
        return expected.strip().lower() == actual.strip().lower()
    return expected == actual


def _text(value: Any) -> str | None:
    return None if value is None else str(value)
