"""The action digest, and a signature verified end to end.

The keys here are generated inside the test, hold nothing, and never leave the
process. They exist because signing code that is never exercised is worse than
no signing code: it looks finished.
"""

from __future__ import annotations

import pytest

from tradesync_core.hyperliquid_signing import (
    EIP712_DOMAIN,
    SigningInputError,
    action_hash,
    signing_payload,
)

ACTION = {
    "type": "order",
    "orders": [
        {"a": 0, "b": True, "p": "78000", "s": "0.01", "r": False, "t": {"limit": {"tif": "Gtc"}}}
    ],
    "grouping": "na",
}
NONCE = 1_788_900_000_000


def test_the_digest_is_deterministic_for_the_same_action_and_nonce() -> None:
    first = action_hash(ACTION, nonce=NONCE)
    second = action_hash(dict(ACTION), nonce=NONCE)
    assert first == second
    assert len(first) == 32


def test_the_nonce_is_part_of_what_is_signed() -> None:
    """A replayed signature is bound to the moment it was made."""
    assert action_hash(ACTION, nonce=NONCE) != action_hash(ACTION, nonce=NONCE + 1)


def test_a_changed_order_changes_the_digest() -> None:
    """The thing being signed is the order, not a summary of it."""
    other = {**ACTION, "orders": [{**ACTION["orders"][0], "s": "9.99"}]}
    assert action_hash(ACTION, nonce=NONCE) != action_hash(other, nonce=NONCE)

    flipped = {**ACTION, "orders": [{**ACTION["orders"][0], "b": False}]}
    assert action_hash(ACTION, nonce=NONCE) != action_hash(flipped, nonce=NONCE)


def test_the_absence_of_a_vault_is_encoded_not_omitted() -> None:
    """The venue distinguishes "no vault" from "vault"; dropping the marker
    would make a personal trade hash like a vault trade."""
    personal = action_hash(ACTION, nonce=NONCE)
    vaulted = action_hash(
        ACTION, nonce=NONCE, vault_address="0x" + "ab" * 20
    )
    assert personal != vaulted


def test_a_malformed_vault_address_is_refused() -> None:
    for bad in ("0xdeadbeef", "not-an-address", "ab" * 19):
        with pytest.raises(SigningInputError):
            action_hash(ACTION, nonce=NONCE, vault_address=bad)


def test_a_non_positive_or_boolean_nonce_is_refused() -> None:
    for bad in (0, -1, True, 1.5, "1788900000000"):
        with pytest.raises(SigningInputError):
            action_hash(ACTION, nonce=bad)  # type: ignore[arg-type]


def test_an_unencodable_action_is_refused_rather_than_silently_altered() -> None:
    with pytest.raises(SigningInputError):
        action_hash({"when": object()}, nonce=NONCE)


def test_the_domain_is_the_venues_and_is_pinned() -> None:
    """chainId 1337 is part of Hyperliquid's scheme, not the chain the assets
    live on. A "correction" here produces signatures the venue rejects."""
    assert EIP712_DOMAIN["name"] == "Exchange"
    assert EIP712_DOMAIN["chainId"] == 1337
    assert EIP712_DOMAIN["version"] == "1"


def test_mainnet_and_testnet_sign_different_messages() -> None:
    """Otherwise a testnet signature would be replayable on mainnet."""
    main = signing_payload(ACTION, nonce=NONCE, mainnet=True)
    test = signing_payload(ACTION, nonce=NONCE, mainnet=False)
    assert main["typed_data"]["message"]["source"] == "a"
    assert test["typed_data"]["message"]["source"] == "b"
    assert main["connection_id"] == test["connection_id"]  # same action
    # but the signed structure differs, which is the point
    assert main["typed_data"] != test["typed_data"]


def test_a_signature_recovers_to_the_signing_address() -> None:
    """End to end, with a key created and discarded inside this test.

    It holds nothing and is never written anywhere. The point is that the
    payload this module builds is actually signable and that the signature
    recovers — untested signing code looks finished and is not.
    """
    from eth_account import Account
    from eth_account.messages import encode_typed_data

    throwaway = Account.create()  # no funds, never persisted
    payload = signing_payload(ACTION, nonce=NONCE)

    signable = encode_typed_data(full_message=payload["typed_data"])
    signed = throwaway.sign_message(signable)

    recovered = Account.recover_message(signable, signature=signed.signature)
    assert recovered == throwaway.address

    # A different action must not verify against this signature.
    other = signing_payload({**ACTION, "grouping": "positionTpsl"}, nonce=NONCE)
    other_signable = encode_typed_data(full_message=other["typed_data"])
    assert Account.recover_message(other_signable, signature=signed.signature) != throwaway.address


def test_the_payload_records_what_was_signed_alongside_the_digest() -> None:
    """A signature with no record of what it covered is not auditable."""
    payload = signing_payload(ACTION, nonce=NONCE)
    assert set(payload) == {"typed_data", "connection_id", "nonce", "mainnet"}
    assert payload["nonce"] == NONCE
    assert len(payload["connection_id"]) == 64
