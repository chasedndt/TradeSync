"""What the signer refuses, and what it will never tell you."""

from __future__ import annotations

import importlib
import os

import pytest
from fastapi.testclient import TestClient

DIGEST = "a" * 64


def load(**env):
    """Import the service under a given environment.

    The key is read once at import and never re-read, so the environment has to
    be set before the module loads. That is the property being tested as much as
    the behaviour: a key that can be swapped at runtime is a key that can be
    swapped by whatever caused the swap.
    """
    for key in ("SIGNER_PRIVATE_KEY", "SIGNING_ENABLED", "SIGNER_MAINNET"):
        os.environ.pop(key, None)
    os.environ.update(env)
    import app.main as main

    return importlib.reload(main)


def request(**over):
    base = {
        "schema_version": "signing_request_v1",
        "payload_digest": DIGEST,
        "envelope_id": "tce_abc",
        "approval_id": "appr_1",
    }
    base.update(over)
    return base


def test_with_no_key_configured_everything_is_refused() -> None:
    main = load()
    client = TestClient(main.app)

    assert client.get("/healthz").json()["key_loaded"] is False
    status = client.get("/signer/status").json()
    assert status["available"] is False
    assert status["address"] is None
    assert "not configured" in status["reason"]

    assert client.post("/sign", json=request()).status_code == 503


def test_a_key_alone_is_not_permission_to_use_it() -> None:
    """Two switches. Having a key configured must not by itself sign anything."""
    from eth_account import Account

    throwaway = Account.create()  # no funds, never persisted
    main = load(SIGNER_PRIVATE_KEY=throwaway.key.hex(), SIGNING_ENABLED="false")
    client = TestClient(main.app)

    status = client.get("/signer/status").json()
    assert status["key_loaded"] is True
    assert status["available"] is False
    assert "SIGNING_ENABLED is false" in status["reason"]

    response = client.post("/sign", json=request())
    assert response.status_code == 503
    assert "will not sign" in response.json()["detail"]


def test_the_key_is_never_returned_by_any_endpoint() -> None:
    from eth_account import Account

    throwaway = Account.create()
    secret = throwaway.key.hex()
    main = load(SIGNER_PRIVATE_KEY=secret, SIGNING_ENABLED="true")
    client = TestClient(main.app)

    bodies = [
        client.get("/healthz").text,
        client.get("/signer/status").text,
        client.post("/sign", json=request()).text,
        client.post("/sign", json=request(payload_digest="nope")).text,
    ]
    for body in bodies:
        assert secret not in body
        assert secret.removeprefix("0x") not in body

    # The address is public by construction and is not withheld.
    assert throwaway.address in client.get("/signer/status").text


def test_an_approval_signs_once() -> None:
    from eth_account import Account

    main = load(SIGNER_PRIVATE_KEY=Account.create().key.hex(), SIGNING_ENABLED="true")
    client = TestClient(main.app)

    first = client.post("/sign", json=request(approval_id="appr_once"))
    assert first.status_code == 200, first.text
    assert first.json()["signature"]["v"] in (27, 28)

    second = client.post("/sign", json=request(approval_id="appr_once"))
    assert second.status_code == 409
    assert "once" in second.json()["detail"]

    # A different approval still works; it is the approval that is spent, not
    # the signer.
    assert client.post("/sign", json=request(approval_id="appr_two")).status_code == 200


def test_single_use_is_enforced_here_not_trusted_from_the_caller() -> None:
    """A caller that has been compromised is exactly the one whose word about
    its own authorisation is worthless."""
    from eth_account import Account

    main = load(SIGNER_PRIVATE_KEY=Account.create().key.hex(), SIGNING_ENABLED="true")
    client = TestClient(main.app)

    client.post("/sign", json=request(approval_id="appr_x"))
    # Same approval, different envelope and digest, still refused.
    replay = client.post(
        "/sign",
        json=request(approval_id="appr_x", envelope_id="tce_other", payload_digest="b" * 64),
    )
    assert replay.status_code == 409


def test_it_will_not_accept_a_payload_it_would_have_to_parse() -> None:
    """The isolation is that it receives a digest and nothing else."""
    from eth_account import Account

    main = load(SIGNER_PRIVATE_KEY=Account.create().key.hex(), SIGNING_ENABLED="true")
    client = TestClient(main.app)

    for bad in ("", "not-hex", "a" * 63, "a" * 65):
        response = client.post("/sign", json=request(payload_digest=bad))
        assert response.status_code == 422, bad
        assert "digest" in response.json()["detail"]


def test_a_request_carrying_its_own_authorisation_is_refused() -> None:
    """Caught by the model, not just by the boundary helper.

    Pydantic drops unknown fields by default, so `force` and `bypass` were
    discarded before the forbidden-field check ever saw them — the check was
    dead code at the HTTP layer while looking like enforcement. The model now
    forbids extras outright.
    """
    from eth_account import Account

    main = load(SIGNER_PRIVATE_KEY=Account.create().key.hex(), SIGNING_ENABLED="true")
    client = TestClient(main.app)

    response = client.post("/sign", json={**request(), "force": True, "bypass": True})
    assert response.status_code == 422
    body = response.text
    assert "force" in body and "bypass" in body


def test_any_unrecognised_field_is_fatal_not_only_the_named_ones() -> None:
    """Guessing which parts of an unfamiliar request to honour is how a
    boundary erodes."""
    from eth_account import Account

    main = load(SIGNER_PRIVATE_KEY=Account.create().key.hex(), SIGNING_ENABLED="true")
    client = TestClient(main.app)

    response = client.post("/sign", json={**request(), "priority": "high"})
    assert response.status_code == 422
    assert "priority" in response.text


def test_a_malformed_key_leaves_the_signer_refusing_rather_than_crashing() -> None:
    """And says nothing about the value, including its length."""
    main = load(SIGNER_PRIVATE_KEY="not-a-key", SIGNING_ENABLED="true")
    client = TestClient(main.app)

    status = client.get("/signer/status").json()
    assert status["key_loaded"] is False
    assert status["available"] is False
    assert "not-a-key" not in client.get("/signer/status").text
    assert client.post("/sign", json=request()).status_code == 503


def test_the_signature_recovers_to_the_advertised_address() -> None:
    from eth_account import Account
    from eth_account.messages import encode_typed_data

    throwaway = Account.create()
    main = load(SIGNER_PRIVATE_KEY=throwaway.key.hex(), SIGNING_ENABLED="true")
    client = TestClient(main.app)

    body = client.post("/sign", json=request(approval_id="appr_rec")).json()
    signature = (
        body["signature"]["r"],
        body["signature"]["s"],
        body["signature"]["v"],
    )
    typed = {
        "domain": main.EIP712_DOMAIN,
        "types": main.AGENT_TYPES,
        "primaryType": "Agent",
        "message": {"source": "a", "connectionId": bytes.fromhex(DIGEST)},
    }
    signable = encode_typed_data(full_message=typed)
    recovered = Account.recover_message(signable, vrs=(signature[2], int(signature[0], 16), int(signature[1], 16)))
    assert recovered == body["address"] == throwaway.address
