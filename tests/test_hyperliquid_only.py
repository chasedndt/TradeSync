from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = "dri" + "ft"
SELF = Path(__file__).relative_to(ROOT).as_posix()


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
        if FORBIDDEN in text.lower():
            violations.append(f"content:{relative}")
    assert violations == [], "removed protocol references remain:\n" + "\n".join(violations)


def test_hyperliquid_is_the_only_execution_service_in_compose() -> None:
    compose = (ROOT / "ops" / "compose.full.yml").read_text(encoding="utf-8").lower()
    assert "exec-hl-svc:" in compose
    assert 'execution_enabled: "false"' in compose
    assert f"exec-{FORBIDDEN}-svc:" not in compose


def test_market_data_known_venues_are_hyperliquid_only() -> None:
    state_api = (ROOT / "services" / "state-api" / "app" / "main.py").read_text(encoding="utf-8")
    assert 'venues = ["hyperliquid"]' in state_api
    assert '"hyperliquid": "http://exec-hl-svc:8004/exec/hl/positions"' in state_api
    assert FORBIDDEN not in state_api.lower()


def test_state_api_routes_execution_to_hyperliquid_only() -> None:
    source = (ROOT / "services" / "state-api" / "app" / "main.py").read_text(encoding="utf-8")
    assert '"hyperliquid": "http://exec-hl-svc:8004/exec/hl/order"' in source
    assert '"side": order_side' in source
    assert '"short": "sell"' in source
    assert FORBIDDEN not in source.lower()


def test_removed_protocol_dependencies_are_absent() -> None:
    requirement_files = [ROOT / "requirements.txt", ROOT / "services" / "ingest-gateway" / "requirements.txt"]
    combined = "\n".join(path.read_text(encoding="utf-8").lower() for path in requirement_files)
    assert FORBIDDEN not in combined
