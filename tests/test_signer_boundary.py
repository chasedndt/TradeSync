"""There is no signer. These tests exist to keep it that way."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from tradesync_core.signer_boundary import (
    FORBIDDEN_REQUEST_FIELDS,
    SCHEMA_VERSION,
    RefusingSigner,
    SignerRefused,
    get_signer,
    validate_signing_request,
)

ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).relative_to(ROOT).as_posix()


def request(**over):
    base = {
        "schema_version": SCHEMA_VERSION,
        "payload_digest": "a" * 64,
        "envelope_id": "tce_abc",
        "approval_id": "chaseos_appr_1",
    }
    base.update(over)
    return base


def test_the_only_signer_refuses_and_says_why() -> None:
    signer = get_signer()
    assert isinstance(signer, RefusingSigner)
    assert signer.available() is False

    with pytest.raises(SignerRefused) as excinfo:
        signer.sign(request())
    assert excinfo.value.code == "no_signer_configured"
    assert "explicit approval" in str(excinfo.value)


def test_there_is_no_configuration_that_makes_it_sign() -> None:
    """Not a stub to be filled in.

    A stub returning a plausible signature in "test mode" would be worse than
    nothing: it would let an execution path be built and tested against
    something that looks like it works.
    """
    signer = RefusingSigner()
    for attempt in (
        request(),
        request(force=True),
        request(bypass=True),
        request(approved=True),
    ):
        with pytest.raises(SignerRefused):
            signer.sign(attempt)


@pytest.mark.parametrize("field", sorted(FORBIDDEN_REQUEST_FIELDS))
def test_a_request_carrying_its_own_authorisation_is_refused(field: str) -> None:
    """It is asking the signer to trust the caller's word for it."""
    with pytest.raises(SignerRefused) as excinfo:
        validate_signing_request(request(**{field: "yes"}))
    assert excinfo.value.code == "authority_claimed"
    assert field in str(excinfo.value)


def test_the_signer_is_handed_a_digest_never_a_payload() -> None:
    """A signer that parses what it signs is not isolated.

    The whole point of the boundary is that it receives one narrow message it
    cannot be attacked through.
    """
    for bad in ("", "not-hex", "a" * 63, "a" * 65, {"order": "buy"}, 12345):
        with pytest.raises(SignerRefused):
            validate_signing_request(request(payload_digest=bad))

    ok = validate_signing_request(request(payload_digest="A" * 64))
    assert ok["payload_digest"] == "a" * 64


def test_a_request_must_name_the_envelope_and_approval_it_belongs_to() -> None:
    """Per-signature authorisation, not per session."""
    for field in ("envelope_id", "approval_id"):
        with pytest.raises(SignerRefused) as excinfo:
            validate_signing_request(request(**{field: ""}))
        assert field in str(excinfo.value)


def test_the_signer_cannot_be_asked_what_it_holds() -> None:
    """No export, no address enumeration, nothing but yes or no."""
    described = RefusingSigner().describe()
    assert described["available"] is False
    assert described["holds_key"] is False
    # Nothing in the description is key material or a path to any.
    text = " ".join(str(v) for v in described.values())
    assert not re.search(r"0x[0-9a-fA-F]{16,}", text)
    assert described["requirements_to_change_this"]


def test_no_private_key_material_is_committed_anywhere() -> None:
    """A guard, not a formality.

    An 0x-prefixed 64-hex string is an EVM private key. A seed phrase is twelve
    or more dictionary words on one line under a mnemonic-shaped name. Neither
    belongs in a repository, and the day one is pasted in "just to test" is the
    day it is in the history forever.
    """
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, text=True, capture_output=True
    ).stdout.splitlines()

    key_shaped = re.compile(r"0x[0-9a-fA-F]{64}\b")
    assignment = re.compile(
        r"(?:private_key|wallet_pk|secret_key|mnemonic|seed_phrase)\s*[:=]\s*['\"][^'\"]{16,}",
        re.IGNORECASE,
    )

    findings: list[str] = []
    for relative in tracked:
        if relative == SELF:
            continue
        path = ROOT / relative
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if key_shaped.search(text):
            findings.append(f"{relative}: 0x-prefixed 64-hex string")
        if assignment.search(text):
            findings.append(f"{relative}: key-shaped assignment")

    assert findings == [], "possible key material committed:\n" + "\n".join(findings)


def test_the_execution_boundary_holds_no_key_today() -> None:
    """HYPERLIQUID_WALLET_PK is read from the environment and nothing else.

    It is unset, so nothing is exposed. This pins that it is never given a
    default, never written to disk, and never logged — the three ways an unset
    secret quietly becomes a set one.
    """
    source = (ROOT / "services" / "exec-hl-svc" / "app" / "main.py").read_text(
        encoding="utf-8"
    )
    assert 'os.getenv("HYPERLIQUID_WALLET_PK")' in source, "key source changed"
    # No default value.
    assert 'os.getenv("HYPERLIQUID_WALLET_PK",' not in source
    # Never printed, logged or returned.
    for leak in ("print(HYPERLIQUID_WALLET_PK", "logger.info(HYPERLIQUID_WALLET_PK",
                 "return HYPERLIQUID_WALLET_PK", '"pk": HYPERLIQUID_WALLET_PK'):
        assert leak not in source, leak
