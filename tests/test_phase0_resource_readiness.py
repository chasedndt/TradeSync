from __future__ import annotations

import json
import subprocess
from pathlib import Path
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "scripts" / "market-command-readiness.ps1"
OVERLAY = ROOT / "ops" / "compose.market-command.yml"


# Shells out to a PowerShell host audit that samples CPU. Under load — a
# concurrent Docker build, say — it exceeds its own timeout, which says
# something about the machine rather than about the code. The other two tests
# in this file read compose files and stay in the unit suite.
@pytest.mark.integration
def test_readiness_audit_is_paper_only_and_fail_closed() -> None:
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-NoEvidenceWrite",
            "-Json",
            "-CpuSampleIntervalSeconds",
            "1",
            "-CpuSampleCount",
            "1",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        # A safety valve against a hang, not a performance assertion. The script
        # audits the host — PowerShell start-up, Docker state, a CPU sample —
        # and takes ~28s on an idle machine here. A 45s budget left 17s of
        # headroom and failed whenever a container happened to be building,
        # which says nothing about the code this test is checking. What it
        # asserts is content: paper_only, and a fail-closed authority block.
        timeout=180,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["schema_version"] == "market_command_phase0_readiness_v1"
    assert payload["mode"] == "paper_only"
    assert payload["authority"] == {
        "live_execution_authorized": False,
        "wallet_authorized": False,
        "credential_access_authorized": False,
        "service_start_authorized": False,
    }
    assert payload["gates"]["live_execution_allowed"] is False
    assert isinstance(payload["gates"]["docker_engine_start_allowed"], bool)
    assert isinstance(payload["gates"]["docker_engine_start_block_reasons"], list)
    assert isinstance(payload["gates"]["core_profile_block_reasons"], list)
    assert payload["storage"]["ollama_model_root"].startswith("E:\\")


def test_compose_overlay_keeps_optional_workloads_profile_gated() -> None:
    text = OVERLAY.read_text(encoding="utf-8")

    assert "profiles: [operator]" in text
    assert "profiles: [evidence]" in text
    assert "profiles: [paper-exec]" in text
    assert "profiles: [analytics]" in text
    assert 'EXECUTION_ENABLED: "false"' in text
    assert 'DRY_RUN: "true"' in text
    assert "mem_limit:" in text
    assert "max-size:" in text


def test_full_compose_uses_existing_postgres_bootstrap_path_and_python_healthcheck() -> None:
    compose = (ROOT / "ops" / "compose.full.yml").read_text(encoding="utf-8")

    assert "./sql:/docker-entrypoint-initdb.d:ro" in compose
    assert "./ops/sql:/docker-entrypoint-initdb.d:ro" not in compose
    assert "profiles: [analytics]" in compose
    # market-data is gated on /readyz, not /healthz. The two answer different
    # questions: /healthz says the process is alive (restarting it would not
    # help), /readyz says the data behind it is fresh enough to serve. Compose
    # uses the healthcheck for "condition: service_healthy", so a dependant
    # must wait on readiness. On 7 Sept the process stayed up while its feed
    # had stalled and a /healthz probe reported the service healthy throughout.
    assert "urllib.request.urlopen('http://localhost:8005/readyz'" in compose
    # Still a python probe rather than curl: the market-data image is
    # python:slim with no curl, so a curl healthcheck fails closed for a reason
    # that has nothing to do with the service. Other images (nginx, the exec
    # boundary) do ship curl and legitimately use it.
    assert 'test: [ "CMD", "curl", "-sf", "http://localhost:8005' not in compose
