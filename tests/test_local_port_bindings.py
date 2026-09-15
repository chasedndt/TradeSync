"""Every host port the compose files publish is bound to 127.0.0.1.

The Cockpit (3000) proxies all of state-api, state-api (8000) accepts changes
without authentication unless an operator token is configured, and Redis (6379)
has no authentication at all. Published on 0.0.0.0, each one is a single host
firewall setting away from whatever network the machine has joined: on
2026-09-15 the host's own firewall configuration, not the compose files, was
what kept them off the Wi-Fi network.

Widening a binding should take a deliberate, reviewed edit to this test.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILES = sorted([ROOT / "docker-compose.yml", *(ROOT / "ops").glob("compose*.yml")])


def _published(path: Path) -> list[tuple[str, object]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
    return [
        (name, entry)
        for name, service in (data.get("services") or {}).items()
        for entry in ((service or {}).get("ports") or [])
    ]


def test_every_compose_file_in_use_is_checked() -> None:
    names = {path.name for path in COMPOSE_FILES}
    assert {
        "docker-compose.yml",
        "compose.full.yml",
        "compose.infra.yml",
        "compose.market-command.yml",
        "compose.ingress.yml",
        "compose.signer.yml",
    } <= names


@pytest.mark.parametrize("path", COMPOSE_FILES, ids=lambda path: path.name)
def test_every_published_port_is_bound_to_loopback(path: Path) -> None:
    wide = []
    for service, entry in _published(path):
        bound = entry.get("host_ip") == "127.0.0.1" if isinstance(entry, dict) else str(entry).startswith("127.0.0.1:")
        if not bound:
            wide.append(f"{service}: {entry}")
    assert not wide, f"{path.name} publishes ports beyond this machine: {wide}"


def test_the_ports_host_tools_use_are_still_published_on_loopback() -> None:
    """Bound, not removed: the host bridges post to 8000 and the operator opens the Cockpit on 3000."""
    full = {service: str(entry) for service, entry in _published(ROOT / "ops" / "compose.full.yml")}
    assert full["state-api"] == "127.0.0.1:8000:8000"
    assert full["cockpit-ui"] == "127.0.0.1:3000:80"


def test_the_tunnel_and_the_signer_publish_nothing() -> None:
    assert _published(ROOT / "ops" / "compose.ingress.yml") == []
    assert _published(ROOT / "ops" / "compose.signer.yml") == []
