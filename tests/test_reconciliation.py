"""Reconciliation reports divergence. It never guesses which side is right."""

from __future__ import annotations

from tradesync_core.reconciliation import SIZE_TOLERANCE_USD, reconcile


def decision(did: str, **over):
    requested = {"symbol": "BTC-PERP", "side": "long", "size_usd": 100.0, "venue": "hyperliquid"}
    requested.update(over)
    return {"id": did, "requested": requested}


def order(did: str, oid: str = "o1", **over):
    request = {"symbol": "BTC-PERP", "side": "long", "size_usd": 100.0, "venue": "hyperliquid"}
    request.update(over)
    return {"id": oid, "decision_id": did, "request": request}


def test_a_clean_reconciliation_is_reported_as_a_result() -> None:
    """"No divergence found" is a fact worth stating, not silence."""
    result = reconcile([decision("d1"), decision("d2")], [order("d1"), order("d2", "o2")])
    assert result["clean"] is True
    assert result["matched"] == 2
    assert result["divergences"] == []
    assert "no divergence" in result["summary"]


def test_a_decision_with_no_order_is_reported_without_guessing_why() -> None:
    """Execution never happened, or happened unrecorded.

    Those have opposite remedies. A reconciliation that picked one would send
    the operator to fix the wrong thing.
    """
    result = reconcile([decision("d1")], [])
    assert result["clean"] is False
    (div,) = result["divergences"]
    assert div["kind"] == "orphan_decision"
    assert div["decision_id"] == "d1"
    assert "opposite remedies" in div["detail"]


def test_an_order_with_no_decision_id_is_an_orphan() -> None:
    """Nothing in this system should be able to produce one."""
    stray = {"id": "o9", "request": {"symbol": "BTC-PERP"}}
    result = reconcile([], [stray])
    (div,) = result["divergences"]
    assert div["kind"] == "orphan_order"
    assert div["order_id"] == "o9"


def test_two_orders_for_one_decision_are_reported() -> None:
    """One approval must not produce two orders.

    A unique constraint should make this impossible; if it appears, the
    constraint is gone or something wrote around it.
    """
    result = reconcile([decision("d1")], [order("d1", "o1"), order("d1", "o2")])
    kinds = {d["kind"] for d in result["divergences"]}
    assert "duplicate_order" in kinds


def test_a_field_mismatch_names_the_field_and_both_values() -> None:
    result = reconcile([decision("d1")], [order("d1", side="short")])
    (div,) = result["divergences"]
    assert div["kind"] == "field_mismatch"
    assert div["field"] == "side"
    assert div["expected"] == "long"
    assert div["actual"] == "short"


def test_every_money_and_direction_field_is_compared() -> None:
    for field, changed in (
        ("symbol", "ETH-PERP"),
        ("side", "short"),
        ("size_usd", 250.0),
        ("venue", "somewhere-else"),
    ):
        result = reconcile([decision("d1")], [order("d1", **{field: changed})])
        assert [d["field"] for d in result["divergences"]] == [field], field


def test_case_differences_in_a_side_are_not_a_different_trade() -> None:
    """A venue may echo a side back capitalised."""
    result = reconcile([decision("d1")], [order("d1", side="LONG")])
    assert result["clean"] is True


def test_size_agrees_within_the_venue_rounding_tolerance() -> None:
    """A venue rounds to its own lot size; that is not a discrepancy."""
    inside = reconcile(
        [decision("d1")], [order("d1", size_usd=100.0 + SIZE_TOLERANCE_USD / 2)]
    )
    assert inside["clean"] is True

    outside = reconcile([decision("d1")], [order("d1", size_usd=100.5)])
    assert outside["clean"] is False
    assert outside["divergences"][0]["field"] == "size_usd"


def test_an_order_whose_decision_predates_the_window_is_not_an_orphan() -> None:
    """Otherwise the query bound manufactures a finding.

    A reconciliation over the last hour will always see orders for decisions
    taken before it. Calling those orphans would report a divergence that is
    entirely an artefact of how far back somebody looked.
    """
    result = reconcile([decision("d2")], [order("d1"), order("d2", "o2")])
    assert result["clean"] is True
    assert result["orders_outside_window"] == ["d1"]


def test_a_malformed_payload_is_reported_rather_than_skipped() -> None:
    result = reconcile([{"id": "d1", "requested": "not a mapping"}], [order("d1")])
    (div,) = result["divergences"]
    assert div["kind"] == "field_mismatch"
    assert "not a mapping" in div["detail"]


def test_a_decision_with_no_id_cannot_be_reconciled_and_is_skipped() -> None:
    """There is nothing to match it against; inventing an id would be worse."""
    result = reconcile([{"requested": {}}, decision("d1")], [order("d1")])
    assert result["decisions"] == 1
    assert result["clean"] is True


def test_reconciliation_reads_only_and_reports_counts() -> None:
    """It compares two records. It cannot place, amend or cancel anything.

    Asserted structurally: the returned shape carries findings and counts, and
    nothing that could be mistaken for an instruction.
    """
    result = reconcile([decision("d1")], [order("d1")])
    assert set(result) == {
        "decisions",
        "orders",
        "matched",
        "divergences",
        "orders_outside_window",
        "clean",
        "summary",
    }
