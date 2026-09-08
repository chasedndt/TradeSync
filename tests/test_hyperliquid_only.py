from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = "dri" + "ft"
SELF = Path(__file__).relative_to(ROOT).as_posix()

# The removed venue's name is also an ordinary English noun, and this codebase
# uses it constantly: documentation drift, clock drift, policy drift. A bare
# substring scan flagged every one of those, so the guard failed on prose it had
# no business failing on and told the operator nothing. It has been red at HEAD.
#
# These patterns look for the name used *as a name* instead.
_VENUE_NOUN = r"(?:protocol|perps?|dex|exchange|program|vaults?|sdk|labs|markets?)"
_VENUE_CONTEXT = r"(?:venue|exchange|protocol|dex|adapter|connector|provider)"
VENUE_REFERENCE = re.compile(
    "|".join(
        (
            # Part of a longer token: driftpy, drift_client, exec-drift-svc.
            r"[A-Za-z0-9_-]" + FORBIDDEN,
            # "(?!s\b)" keeps the English plural out: "drifts apart" is
            # prose, while "driftsdk" would still be caught.
            FORBIDDEN + r"(?!s\b)[A-Za-z0-9_-]",
            # A quoted or dotted literal: "drift", 'drift', drift.trade.
            r"[\"']" + FORBIDDEN + r"[\"']",
            FORBIDDEN + r"\.[a-z_]",
            # Named alongside venue vocabulary, directly adjacent.
            FORBIDDEN + r" " + _VENUE_NOUN + r"\b",
            _VENUE_CONTEXT + r"\W{0,2}" + FORBIDDEN + r"\b",
        )
    ),
    re.IGNORECASE,
)



def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, text=True, capture_output=True
    )
    return [line for line in result.stdout.splitlines() if line and line != SELF]


def test_removed_protocol_has_no_tracked_path_or_text_reference() -> None:
    violations: list[str] = []
    for relative in tracked_files():
        path = ROOT / relative
        if not path.exists():
            continue
        if FORBIDDEN in relative.lower():
            violations.append(f"path:{relative}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        match = VENUE_REFERENCE.search(text)
        if match is not None:
            violations.append(f"content:{relative}: {match.group(0)!r}")
    assert violations == [], "removed protocol references remain:\n" + "\n".join(violations)


def test_the_guard_still_recognises_a_real_venue_reference() -> None:
    """Proof that narrowing the scan did not turn the guard into a no-op.

    Each reappearance below is how the removed venue would actually come back;
    each prose line is how the English word legitimately appears here today.
    """
    for reappearance in (
        f"from {FORBIDDEN}py.types import Order",
        f"exec-{FORBIDDEN}-svc:",
        f'venues = ["hyperliquid", "{FORBIDDEN}"]',
        f"{FORBIDDEN} protocol markets are quoted in USDC",
        f"venue: {FORBIDDEN}",
        f"https://{FORBIDDEN}.trade/api",
        f"{FORBIDDEN}_client = build_client()",
    ):
        assert VENUE_REFERENCE.search(reappearance), reappearance

    for prose in (
        "There is documentation drift that must be reconciled",
        "Runtime controls: circuit breaker, rate limits, clock drift, API health",
        "IMPLEMENTED in source / policy drift exists",
        "## Known Drift, Defects, and Planning Risks",
        "Duplicated data always drifts apart",
    ):
        assert not VENUE_REFERENCE.search(prose), prose


def test_hyperliquid_is_the_only_execution_service_in_compose() -> None:
    compose = (ROOT / "ops" / "compose.full.yml").read_text(encoding="utf-8").lower()
    assert "exec-hl-svc:" in compose
    assert 'execution_enabled: "false"' in compose
    assert f"exec-{FORBIDDEN}-svc:" not in compose


def test_market_data_known_venues_are_hyperliquid_only() -> None:
    state_api = (ROOT / "services" / "state-api" / "app" / "main.py").read_text(encoding="utf-8")
    assert 'venues = ["hyperliquid"]' in state_api
    assert '"hyperliquid": "http://exec-hl-svc:8004/exec/hl/positions"' in state_api
    # Same precise matcher as the tracked-files scan. A bare substring check
    # here fired on the ordinary English word in a code comment, which is the
    # defect that had this guard red at HEAD.
    assert VENUE_REFERENCE.search(state_api) is None


def test_state_api_routes_execution_to_hyperliquid_only() -> None:
    source = (ROOT / "services" / "state-api" / "app" / "main.py").read_text(encoding="utf-8")
    assert '"hyperliquid": "http://exec-hl-svc:8004/exec/hl/order"' in source
    assert '"side": order_side' in source
    assert '"short": "sell"' in source
    assert VENUE_REFERENCE.search(source) is None


def test_removed_protocol_dependencies_are_absent() -> None:
    requirement_files = [ROOT / "requirements.txt", ROOT / "services" / "ingest-gateway" / "requirements.txt"]
    combined = "\n".join(path.read_text(encoding="utf-8").lower() for path in requirement_files)
    assert FORBIDDEN not in combined
