"""A Pine receipt may describe a setup. It may not grant itself authority."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tradesync_core.paper_ledger import PaperLedgerError, _validate_candidate
from tradesync_core.strike_zone import (
    FORBIDDEN_RECEIPT_FIELDS,
    ReceiptError,
    to_trade_candidate,
    validate_receipt,
)

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


def receipt(**over):
    base = {
        "indicator": "StrikeZone Crypto v3",
        "ticker": "BTCUSD.P",
        "direction": "long",
        "interval": "60",
        "activation": {
            "operator": "all",
            "conditions": [{"field": "close", "operator": "above", "value": 65000}],
        },
        "invalidation": {
            "operator": "any",
            "conditions": [{"field": "close", "operator": "below", "value": 64200}],
        },
    }
    base.update(over)
    return base


def candidate(**over):
    return to_trade_candidate(
        validate_receipt(receipt(**over)),
        canonical_symbol="BTC-USD-PERP",
        asset="BTC",
        observed_at=NOW,
        source_item_id="quar_001",
    )


def test_a_valid_receipt_becomes_a_candidate_the_paper_ledger_accepts() -> None:
    """The acceptance criterion is the ledger's own validator, not mine.

    Two independent locks on the same invariants: this adapter writes them, and
    paper_ledger re-checks them without trusting who built the candidate.
    """
    doc = candidate()
    assert doc["schema_version"] == "trade_candidate_v1"
    # Raises if any authority invariant is violated.
    window = _validate_candidate(doc)
    assert window.evidence_cutoff <= window.valid_from < window.expires_at


def test_the_candidate_is_review_only_at_level_zero_with_execution_disabled() -> None:
    doc = candidate()
    assert doc["candidate"]["status"] == "review_only"
    assert doc["governance"]["authority_level"] == "level_0_observation_only"
    assert doc["governance"]["operator_approval_status"] == "not_requested"
    assert doc["governance"]["self_authority_change_allowed"] is False
    assert doc["execution"]["execution_gateway_status"] == "disabled"
    assert doc["execution"]["live_execution_allowed"] is False
    assert doc["execution"]["order_creation_allowed"] is False
    assert doc["execution"]["order_id"] is None
    assert doc["risk"]["risk_status"] == "not_evaluated"


@pytest.mark.parametrize("field", sorted(FORBIDDEN_RECEIPT_FIELDS))
def test_a_receipt_setting_its_own_authority_is_refused_by_name(field: str) -> None:
    """Refused, not overwritten.

    A Pine script is a text file on a third party's server that anyone holding
    the alert URL can aim at this endpoint. Silently overwriting the field would
    accept the request and discard the evidence that it was made.
    """
    with pytest.raises(ReceiptError) as excinfo:
        validate_receipt(receipt(**{field: True}))
    assert excinfo.value.code == "authority_claimed"
    assert field in str(excinfo.value)


def test_authority_cannot_be_smuggled_in_and_survive_to_the_candidate() -> None:
    """Even if validation were bypassed, the fields are written not copied."""
    smuggled = validate_receipt(receipt())
    smuggled["execution"] = {"live_execution_allowed": True}
    smuggled["governance"] = {"authority_level": "level_3_execute"}

    doc = to_trade_candidate(
        smuggled, canonical_symbol="BTC-USD-PERP", asset="BTC", observed_at=NOW
    )
    assert doc["execution"]["live_execution_allowed"] is False
    assert doc["governance"]["authority_level"] == "level_0_observation_only"
    _validate_candidate(doc)


def test_an_unknown_direction_is_refused() -> None:
    with pytest.raises(ReceiptError) as excinfo:
        validate_receipt(receipt(direction="sideways"))
    assert excinfo.value.code == "unknown_direction"

    # Case and whitespace are normalised rather than refused.
    assert validate_receipt(receipt(direction="  SHORT "))["direction"] == "short"


def test_a_receipt_with_no_activation_condition_is_refused() -> None:
    """It could never activate, so it would be a record of nothing."""
    with pytest.raises(ReceiptError) as excinfo:
        validate_receipt(receipt(activation={"operator": "all", "conditions": []}))
    assert excinfo.value.code == "no_activation"

    with pytest.raises(ReceiptError):
        validate_receipt(receipt(activation=None))


def test_a_condition_the_evaluator_cannot_read_is_refused() -> None:
    """Otherwise the candidate is stored and silently never activates."""
    for bad, code in (
        ({"field": "rsi", "operator": "above", "value": 70}, "unknown_condition_field"),
        ({"field": "close", "operator": "crosses", "value": 1}, "unknown_condition_operator"),
        ({"field": "close", "operator": "above", "value": "65000"}, "non_numeric_condition"),
        ({"field": "close", "operator": "above", "value": True}, "non_numeric_condition"),
    ):
        with pytest.raises(ReceiptError) as excinfo:
            validate_receipt(receipt(activation={"operator": "all", "conditions": [bad]}))
        assert excinfo.value.code == code, bad


def test_a_missing_required_field_is_named() -> None:
    for field in ("indicator", "ticker", "direction"):
        body = receipt()
        del body[field]
        with pytest.raises(ReceiptError) as excinfo:
            validate_receipt(body)
        assert field in str(excinfo.value)


def test_the_evidence_cutoff_is_when_the_alert_existed() -> None:
    """A candidate must not be scored on candles the Pine script never saw."""
    doc = candidate()
    assert doc["evidence_cutoff_utc"] == "2026-09-08T12:00:00Z"
    assert doc["valid_from_utc"] == doc["evidence_cutoff_utc"]
    assert doc["expires_at_utc"] == "2026-09-08T16:00:00Z"


def test_a_naive_timestamp_is_refused() -> None:
    """A cutoff without an offset is ambiguous by hours, which is the window."""
    with pytest.raises(ReceiptError) as excinfo:
        to_trade_candidate(
            validate_receipt(receipt()),
            canonical_symbol="BTC-USD-PERP",
            asset="BTC",
            observed_at=datetime(2026, 9, 8, 12, 0),
        )
    assert excinfo.value.code == "naive_timestamp"


def test_a_non_positive_validity_is_refused() -> None:
    with pytest.raises(ReceiptError):
        to_trade_candidate(
            validate_receipt(receipt()),
            canonical_symbol="BTC-USD-PERP",
            asset="BTC",
            observed_at=NOW,
            validity=timedelta(0),
        )


def test_the_candidate_id_is_deterministic_for_the_same_alert() -> None:
    """The same alert re-delivered must not mint a second candidate."""
    assert candidate()["candidate_id"] == candidate()["candidate_id"]
    changed = candidate(
        activation={
            "operator": "all",
            "conditions": [{"field": "close", "operator": "above", "value": 66000}],
        }
    )
    assert changed["candidate_id"] != candidate()["candidate_id"]


def test_lineage_records_what_produced_the_candidate() -> None:
    doc = candidate()
    assert doc["lineage"]["indicator"] == "StrikeZone Crypto v3"
    assert doc["lineage"]["source_item_ids"] == ["quar_001"]
    # Nothing is claimed to come from a TradeSync signal, because nothing did.
    assert doc["lineage"]["signal_ids"] == []


def test_a_raw_alert_body_cannot_be_passed_straight_to_the_builder() -> None:
    """Validation is not optional, and skipping it is caught rather than assumed."""
    with pytest.raises(ReceiptError) as excinfo:
        to_trade_candidate(
            receipt(), canonical_symbol="BTC-USD-PERP", asset="BTC", observed_at=NOW
        )
    assert excinfo.value.code == "unvalidated_receipt"


def test_the_ledger_rejects_a_candidate_whose_authority_was_tampered_with() -> None:
    """Proves the second lock is real, not decorative."""
    doc = candidate()
    doc["execution"]["live_execution_allowed"] = True
    with pytest.raises(PaperLedgerError) as excinfo:
        _validate_candidate(doc)
    assert excinfo.value.code == "authority_invariant_violation"
