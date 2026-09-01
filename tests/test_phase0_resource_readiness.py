from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "scripts" / "market-command-readiness.ps1"
OVERLAY = ROOT / "ops" / "compose.market-command.yml"


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
        timeout=45,
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
    assert "urllib.request.urlopen('http://localhost:8005/healthz'" in compose
