"""Secret-shaped text a Hermes job prints never reaches state-api: both host bridges redact before posting.

A job's output, its run and delivery errors and its prompt are whatever the
fleet wrote. Knowledge Intake and the Fleet panel display what state-api
stores, so a token, key or webhook URL has to be removed on the host, before
the request is made. Each bridge runs here against a temporary Hermes tree and
a client that records what it would have sent and sends nothing.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _service_import import load_module_by_path  # noqa: E402

output_bridge = load_module_by_path("hermes_output_bridge_tool", "tools/hermes_output_bridge.py")
fleet_bridge = load_module_by_path("hermes_fleet_bridge_tool", "tools/hermes_fleet_bridge.py")

JOB_ID = "0123456789ab"
# Synthetic values in the shapes tradesync_core.job_errors recognises.
TOKEN = f"{'x' * 24}.abcdef.{'y' * 38}"
WEBHOOK_SECRET = "abcDEF_-9ghiJKL"
WEBHOOK = f"https://discord.com/api/webhooks/123456789012345678/{WEBHOOK_SECRET}"
PREFIXED_KEY = "sk-" + "k" * 24
LABELLED_KEY = "supersecretvalue1"
BEARER = "abcdefghijklmnop"
SECRETS = ("x" * 24, "y" * 38, WEBHOOK_SECRET, PREFIXED_KEY, LABELLED_KEY, BEARER)
LEAKY = (
    f"Posted the digest with {TOKEN} to {WEBHOOK}\n"
    f"Retried with api_key={LABELLED_KEY}, then Authorization: Bearer {BEARER} and {PREFIXED_KEY}\n"
)


class _Response:
    def __init__(self, body: dict) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._body


class _Client:
    """Records what a bridge would send to state-api; sends nothing."""

    opened: list["_Client"] = []

    def __init__(self, *args, headers=None, **kwargs) -> None:
        self.headers = dict(headers or {})
        self.posted: list[tuple[str, dict]] = []
        _Client.opened.append(self)

    def __enter__(self) -> "_Client":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def post(self, url, json=None, **kwargs) -> _Response:
        self.posted.append((url, json))
        return _Response({"accepted": True})

    def get(self, url, params=None, **kwargs) -> _Response:
        return _Response({"directives": []})


def _posted(path_suffix: str = "") -> list[dict]:
    return [body for client in _Client.opened for url, body in client.posted if url.endswith(path_suffix)]


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    # Never the operator's runtime.env: the token helper must find nothing to send.
    monkeypatch.delenv("STATE_API_OPERATOR_TOKEN", raising=False)
    monkeypatch.setenv("TRADESYNC_RUNTIME_ENV", str(tmp_path / "no-runtime.env"))
    _Client.opened = []
    monkeypatch.setattr(output_bridge.httpx, "Client", _Client)
    yield
    assert all(client.headers == {} for client in _Client.opened)


def test_the_output_bridge_posts_the_job_output_whole_with_secret_shaped_text_removed(tmp_path, monkeypatch) -> None:
    output_dir = tmp_path / "cron" / "output"
    output_dir.mkdir(parents=True)
    report = "## BTC digest\n" + LEAKY + "BTC held the 21-day EMA. " * 100 + "End of digest."
    (output_dir / f"{JOB_ID}_20260915_101500.txt").write_text(report, encoding="utf-8")
    state = tmp_path / "bridge-state.json"
    state.write_text(json.dumps({"cursor_mtime_ns": 1}), encoding="utf-8")
    monkeypatch.setattr(output_bridge, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(output_bridge, "JOBS_FILE", tmp_path / "jobs.json")
    monkeypatch.setattr(output_bridge, "CHANNELS_FILE", tmp_path / "channels.json")
    monkeypatch.setattr(output_bridge, "STATE_FILE", state)

    counts = output_bridge.run_pass()

    posted = _posted("/state/quarantine")
    assert counts["accepted"] == 1 and len(posted) == 1
    content = posted[0]["payload"]["content"]
    for secret in SECRETS:
        assert secret not in json.dumps(posted)
    assert content.count("[redacted]") >= 5
    # Redaction is not truncation: the evidence after the secrets is kept whole.
    assert content.startswith("## BTC digest") and content.endswith("End of digest.")


def test_the_fleet_bridge_snapshot_carries_no_secret_shaped_text(tmp_path, monkeypatch) -> None:
    cron = tmp_path / "cron"
    cron.mkdir()
    job = {
        "id": JOB_ID,
        "name": "desk digest",
        "prompt": f"Summarise the desk and post it to {WEBHOOK} " + "with detail " * 60,
        "last_error": f"Discord refused {TOKEN}",
        "last_delivery_error": f"api_key={LABELLED_KEY}",
    }
    (cron / "jobs.json").write_text(json.dumps({"jobs": [job]}), encoding="utf-8")
    db = sqlite3.connect(cron / "executions.db")
    db.execute("CREATE TABLE executions (id TEXT, job_id TEXT, status TEXT, claimed_at TEXT, started_at TEXT, finished_at TEXT, error TEXT)")
    db.execute(
        "INSERT INTO executions VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("run-1", JOB_ID, "failed", "2026-09-15T10:00:00", "2026-09-15T10:00:01", "2026-09-15T10:00:03",
         f"HTTP 401: Authorization: Bearer {BEARER} refused; key {PREFIXED_KEY}"),
    )
    db.commit()
    db.close()
    usage = {"fire_id": "fire-1", "job_id": JOB_ID, "ts": "2026-09-15T10:00:00Z", "error": f"delivery to {WEBHOOK} failed"}
    (cron / "usage_audit.jsonl").write_text(json.dumps(usage) + "\n", encoding="utf-8")
    monkeypatch.setattr(fleet_bridge, "HERMES_HOME", tmp_path)
    monkeypatch.setattr(fleet_bridge, "CRON", cron)

    fleet_bridge.run_pass()

    snapshots = _posted("/state/fleet/snapshot")
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    for secret in SECRETS:
        assert secret not in json.dumps(snapshot)
    assert snapshot["runs"][0]["error"].startswith("HTTP 401")
    assert snapshot["usage"][0]["error"].endswith("failed")
    description = snapshot["jobs"][0]["description"]
    assert description.startswith("Summarise the desk") and len(description) == fleet_bridge.DESCRIPTION_CHARS
