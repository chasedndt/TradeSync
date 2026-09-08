"""The boundary an isolated signer must sit behind. Deliberately non-functional.

There is no signer here, and this module cannot become one. It holds no key,
loads no key, generates no key, and has no code path that produces a signature.
What it defines is the **shape of the hole** a real signer would have to fit,
and a null implementation that refuses everything.

## Why specify a boundary for something that is not being built

Because the placement it replaces is already wrong, and writing it down is what
stops the wrong one being improvised later.

Today `HYPERLIQUID_WALLET_PK` is read in `services/exec-hl-svc/app/main.py` —
the same process that accepts order requests over HTTP from state-api, makes
outbound calls to the venue, and parses the venue's replies. A private key in
that process is reachable from every bug in any of those three surfaces. It is
unset, so nothing is exposed; but the shape is wrong, and a shape stays wrong
quietly until the day somebody sets the variable.

"Isolated" means the key lives somewhere that:

1. **Receives only signing requests.** Not orders, not JSON from a venue, not
   anything it has to interpret. One narrow message type.
2. **Cannot be asked what it holds.** No export, no address enumeration, no
   "check the key is loaded" that answers with anything but yes or no.
3. **Refuses by default.** An unconfigured signer refuses; it does not fall
   through to a permissive path.
4. **Is authorised per signature, not per session.** One approval, one
   signature, and the approval is consumed — which is exactly the property
   `control_envelope.py` already enforces for paper evaluations.

## What is deliberately absent

The implementation. Gate 1.2 returned NEGATIVE — no demonstrated skill in any
regime at any horizon — and the operator's authority constraint requires
explicit approval for any key, signer or wallet. Neither condition is met, so
the only implementation in this repository is the one below that refuses.

That absence is load-bearing. A stub that returned a plausible-looking signature
in "test mode" would be worse than nothing: it would let the rest of an
execution path be built and tested against something that looks like it works.
"""

from __future__ import annotations

from typing import Any, Mapping

SCHEMA_VERSION = "signing_request_v1"

# The only thing a signer may be asked for. Not an order, not a payload to
# interpret — a digest that was computed on the other side of the boundary, so
# the signer never parses anything it could be attacked through.
REQUIRED_REQUEST_FIELDS = ("schema_version", "payload_digest", "envelope_id", "approval_id")

# Fields a signing request must never carry. A request that brings its own
# authorisation is asking the signer to trust the caller's word for it.
FORBIDDEN_REQUEST_FIELDS = frozenset(
    {
        "approved",
        "authority",
        "bypass",
        "execution_authority",
        "force",
        "key",
        "private_key",
        "seed",
        "mnemonic",
        "skip_approval",
    }
)


class SignerRefused(RuntimeError):
    """A signing request was refused, with the reason stated."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def validate_signing_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """Check the shape of a signing request. Signs nothing.

    Exists so that the request contract is testable and fixed before any signer
    is built against it. A boundary agreed after the fact is a boundary shaped
    by whatever the first implementation happened to do.
    """
    if not isinstance(request, Mapping):
        raise SignerRefused("malformed_request", "signing request must be an object")

    if request.get("schema_version") != SCHEMA_VERSION:
        raise SignerRefused(
            "unsupported_schema",
            f"expected {SCHEMA_VERSION}, got {request.get('schema_version')!r}",
        )

    reached_for = sorted(FORBIDDEN_REQUEST_FIELDS.intersection(request))
    if reached_for:
        raise SignerRefused(
            "authority_claimed",
            "signing request carries fields that ask the signer to trust the "
            "caller's word for its own authorisation: " + ", ".join(reached_for),
        )

    missing = [f for f in REQUIRED_REQUEST_FIELDS if not request.get(f)]
    if missing:
        raise SignerRefused(
            "incomplete_request", "signing request is missing: " + ", ".join(missing)
        )

    digest = str(request["payload_digest"])
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
        # A digest, not a payload. If the signer ever accepts something it has
        # to parse to understand, the isolation is gone.
        raise SignerRefused(
            "not_a_digest",
            "payload_digest must be a 64-character hex sha256; a signer that "
            "accepts a payload it has to parse is not isolated",
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "payload_digest": digest.lower(),
        "envelope_id": str(request["envelope_id"]),
        "approval_id": str(request["approval_id"]),
    }


class RefusingSigner:
    """The only signer in this repository. It refuses everything.

    Not a stub to be filled in later, and not a test double. It is the correct
    implementation for the current state of the system: no key exists, no
    approval exists for one to exist, and the measurement gate that would
    justify one returned negative.

    ``sign`` raises. There is no configuration that makes it return a signature,
    which is why there is no configuration to get wrong.
    """

    #: Stated on the instance so a caller can report *why* without catching.
    reason = (
        "No signer is configured and none is authorised. The operator's "
        "authority constraint requires explicit approval for any key, signer or "
        "wallet, and skill gate 1.2 returned negative."
    )

    def available(self) -> bool:
        return False

    def describe(self) -> dict[str, Any]:
        """What a caller can learn. Notably not whether a key exists."""
        return {
            "signer": "refusing",
            "available": False,
            "holds_key": False,
            "reason": self.reason,
            "requirements_to_change_this": [
                "explicit operator approval for a key, signer or wallet",
                "a passing skill gate (1.2 currently returns negative)",
                "a signer process that receives only signing requests",
                "per-signature authorisation, consumed once",
            ],
        }

    def sign(self, request: Mapping[str, Any]) -> str:
        """Always raises. Validates first, so a malformed request is named."""
        validate_signing_request(request)
        raise SignerRefused("no_signer_configured", self.reason)


def get_signer() -> RefusingSigner:
    """The signer for this system.

    A single entry point, so that introducing a real signer is one visible edit
    in one place rather than a capability that appears wherever somebody needed
    it.
    """
    return RefusingSigner()
