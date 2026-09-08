"""Hyperliquid EIP-712 action hashing, separated from anything that holds a key.

This module computes the **digest** an exchange action must be signed over. It
never sees a private key, and that separation is the point: the digest can be
computed anywhere — including in the process that builds the order — while
signing happens behind the isolation boundary with nothing but a 32-byte hash
crossing it.

The scheme is Hyperliquid's, not ours. An action is msgpack-encoded, a nonce and
optional vault address are appended, the whole thing is keccak-hashed, and that
hash is signed under an EIP-712 domain whose name is ``Exchange`` and whose
chainId is 1337 regardless of the actual chain. Those constants are the venue's;
getting any of them wrong produces a signature the venue rejects, which is the
safe direction to fail but still a failure.

Hand-rolling EIP-712 would be a bad idea, so the encoding below is the documented
Hyperliquid connection-id construction and the signing itself is left to
``eth_account``, which is the reference implementation for the primitive.
"""

from __future__ import annotations

from typing import Any, Mapping

import msgpack
from eth_utils import keccak

# Hyperliquid's own domain. chainId 1337 is what the venue expects for exchange
# actions and is not the chain the assets live on; it is part of the scheme.
EIP712_DOMAIN = {
    "name": "Exchange",
    "version": "1",
    "chainId": 1337,
    "verifyingContract": "0x0000000000000000000000000000000000000000",
}

AGENT_TYPES = {
    "Agent": [
        {"name": "source", "type": "string"},
        {"name": "connectionId", "type": "bytes32"},
    ]
}

MAINNET_SOURCE = "a"
TESTNET_SOURCE = "b"


class SigningInputError(ValueError):
    """The action could not be encoded, with the reason stated."""


def action_hash(
    action: Mapping[str, Any],
    *,
    nonce: int,
    vault_address: str | None = None,
) -> bytes:
    """The 32-byte connection id for one exchange action.

    ``nonce`` is a millisecond timestamp and is part of what is signed, so a
    replayed signature is bound to the moment it was made.

    ``vault_address`` is appended when trading a vault rather than the signer's
    own account. Absent, a single zero byte marks its absence — the venue
    distinguishes the two, so this cannot be dropped.
    """
    if not isinstance(action, Mapping):
        raise SigningInputError("action must be a mapping")
    if not isinstance(nonce, int) or isinstance(nonce, bool) or nonce <= 0:
        raise SigningInputError("nonce must be a positive integer (milliseconds)")

    try:
        data = msgpack.packb(dict(action), use_bin_type=True)
    except (TypeError, ValueError) as exc:
        raise SigningInputError(f"action is not msgpack-encodable: {exc}") from exc

    data += nonce.to_bytes(8, "big")
    if vault_address is None:
        data += b"\x00"
    else:
        cleaned = vault_address.lower().removeprefix("0x")
        if len(cleaned) != 40:
            raise SigningInputError("vault_address must be a 20-byte hex address")
        data += b"\x01" + bytes.fromhex(cleaned)

    return keccak(data)


def signing_payload(
    action: Mapping[str, Any],
    *,
    nonce: int,
    vault_address: str | None = None,
    mainnet: bool = True,
) -> dict[str, Any]:
    """The full EIP-712 structure to be signed, and its digest.

    Returns both, so the caller can record exactly what was signed alongside the
    digest that crossed the boundary. A signature with no record of what it
    covered is not auditable.
    """
    connection_id = action_hash(action, nonce=nonce, vault_address=vault_address)
    message = {
        "source": MAINNET_SOURCE if mainnet else TESTNET_SOURCE,
        "connectionId": connection_id,
    }
    typed = {
        "domain": EIP712_DOMAIN,
        "types": AGENT_TYPES,
        "primaryType": "Agent",
        "message": message,
    }
    return {
        "typed_data": typed,
        "connection_id": connection_id.hex(),
        "nonce": nonce,
        "mainnet": mainnet,
    }
