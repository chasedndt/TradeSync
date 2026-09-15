"""What the Fleet page shows of each Hermes job's runs and outputs, shaped from the read model's rows.

Pure: rows in, plain data out. A run is running while the run ledger has it
claimed or started and not finished. Its elapsed time counts to now, and a
running run that the newest bridge snapshot no longer carried is flagged,
because the ledger only knows what the bridge last posted. Stored output text is
shown as stored, except that anything shaped like a token, key or webhook is
masked (``tradesync_core.job_errors.redact``) and the number masked is stated;
nothing is added to it.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from tradesync_core.job_errors import redact

TERMINAL = frozenset({"completed", "failed", "unknown", "cancelled", "canceled", "error", "timeout", "skipped", "interrupted"})
SNAPSHOT_TOLERANCE_S = 120  # rows re-posted by one bridge pass carry snapshot times within this of each other
FIRST_LINES = 6
LINE_CHARS = 400
OUTPUT_SLACK_S = 5  # an output file is written as its run finishes
BRIDGE_GRACE_S = 300  # the output bridge posts every two minutes; a younger run's output may still be on its way
BRIDGE_EVERY_S = {"fleet": 300, "outputs": 120}
NOTE = ("Runs and model calls are the host fleet bridge's snapshots of the fleet's execution ledger and usage audit, so "
        "running means running as of the snapshot time shown. Outputs are what the output bridge stored in quarantine; "
        "silent runs are not stored. Anything shaped like a token, key or webhook in errors and output text is masked.")
TEXT_NOTE = ("The output as the output bridge stored it in quarantine, with anything shaped like a token, key or webhook "
             "masked. Nothing is added to it.")


def iso(value: Any) -> str | None:
    if not isinstance(value, datetime):
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()


def age_s(value: Any, now: datetime) -> int | None:
    return max(0, int((now - value).total_seconds())) if isinstance(value, datetime) else None


def loads(value: Any) -> Any:
    if isinstance(value, (str, bytes)):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def is_running(run: Mapping[str, Any]) -> bool:
    return run.get("finished_at") is None and str(run.get("status") or "").lower() not in TERMINAL


def run_view(run: Mapping[str, Any], now: datetime, runs_snapshot_at: datetime | None) -> dict[str, Any]:
    view: dict[str, Any] = {
        "id": str(run["id"]), "status": run.get("status"), "claimed_at": iso(run.get("claimed_at")),
        "started_at": iso(run.get("started_at")), "finished_at": iso(run.get("finished_at")),
        "duration_ms": run.get("duration_ms"), "error": redact(run.get("error")),
    }
    if is_running(run):
        snapshot_at = run.get("snapshot_at")
        view.update(running=True, elapsed_s=age_s(run.get("started_at") or run.get("claimed_at"), now),
                    in_latest_snapshot=bool(isinstance(snapshot_at, datetime) and isinstance(runs_snapshot_at, datetime)
                                            and (runs_snapshot_at - snapshot_at).total_seconds() <= SNAPSHOT_TOLERANCE_S))
    return view


def masked(text: str) -> tuple[str, int]:
    """The text with secret-shaped substrings masked, and how many were masked."""
    shown = redact(text, limit=None) or ""
    return shown, shown.count("[redacted]") - text.count("[redacted]")


def output_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    """One stored output without its full text: when, how big, where it went, whether intake kept it, its first lines."""
    payload = loads(row.get("payload")) or {}
    content = str(payload.get("content") or "")
    shown, count = masked(content)
    delivery = payload.get("delivery") if isinstance(payload.get("delivery"), Mapping) else {}
    reasons = loads(row.get("reasons")) or []
    head = [line for line in shown.splitlines() if line.strip()][:FIRST_LINES]
    return {
        "id": str(row["id"]), "job_id": payload.get("job_id"), "agent": payload.get("agent"),
        "received_at": iso(row.get("received_at")), "observed_at": iso(row.get("observed_at")),
        "ran_at_stamp": payload.get("ran_at_stamp") or None,
        "bytes": len(content.encode("utf-8")), "lines": len(content.splitlines()),
        "truncated": bool(payload.get("content_truncated")), "accepted": bool(row.get("accepted")),
        "refused_because": [r["code"] for r in reasons if isinstance(r, Mapping) and r.get("code")],
        "delivery": {"kind": delivery.get("kind"), "channel_label": delivery.get("channel_label")},
        "first_lines": [line[:LINE_CHARS] for line in head],
        "masked": count,
    }


def output_text(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = loads(row.get("payload")) or {}
    shown, _ = masked(str(payload.get("content") or ""))
    return {**output_summary(row), "text": shown, "note": TEXT_NOTE}


def fire_view(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {"ts": iso(row.get("ts")), "model": row.get("model"), "duration_ms": row.get("duration_ms"),
            "silent": row.get("response_silent"), "deliver_target": row.get("deliver_target"), "error": redact(row.get("error"))}


def later_runs_without_output(runs: Sequence[Mapping[str, Any]], output_at: datetime | None, now: datetime) -> int:
    """Finished runs after the newest stored output, old enough that the output bridge would have posted theirs."""
    if output_at is None:
        return 0
    return sum(1 for r in runs if isinstance(r.get("finished_at"), datetime)
               and r["finished_at"] > output_at + timedelta(seconds=OUTPUT_SLACK_S)
               and (now - r["finished_at"]).total_seconds() > BRIDGE_GRACE_S)


def snapshot_view(row: Mapping[str, Any] | None, now: datetime) -> dict[str, Any]:
    out: dict[str, Any] = {"bridge_every_s": BRIDGE_EVERY_S}
    for key in ("runs_snapshot_at", "jobs_snapshot_at", "usage_newest_at", "outputs_received_at"):
        value = row.get(key) if row else None
        out[key], out[key[:-3] + "_age_s"] = iso(value), age_s(value, now)
    return out


def activity_payload(run_rows: Sequence[Mapping[str, Any]], running_rows: Sequence[Mapping[str, Any]],
                     outputs: Mapping[str, dict[str, Any]], fire_rows: Sequence[Mapping[str, Any]],
                     snapshot_row: Mapping[str, Any] | None, now: datetime, outputs_since: datetime | None) -> dict[str, Any]:
    runs_snapshot_at = snapshot_row.get("runs_snapshot_at") if snapshot_row else None
    runs_by_job: dict[str, list[Mapping[str, Any]]] = {}
    for row in run_rows:
        runs_by_job.setdefault(row["job_id"], []).append(row)
    running_by_job: dict[str, list[Mapping[str, Any]]] = {}
    for row in running_rows:
        running_by_job.setdefault(row["job_id"], []).append(row)
    fires = {row["job_id"]: row for row in fire_rows}
    jobs: dict[str, Any] = {}
    for job_id in sorted(set(runs_by_job) | set(running_by_job) | set(outputs) | set(fires)):
        runs, summary = runs_by_job.get(job_id, []), outputs.get(job_id)
        output_at = summary.get("observed_at") or summary.get("received_at") if summary else None
        jobs[job_id] = {
            "running": [run_view(r, now, runs_snapshot_at) for r in running_by_job.get(job_id, [])],
            "runs": [run_view(r, now, runs_snapshot_at) for r in runs],
            "latest_output": summary,
            "later_runs_without_output": later_runs_without_output(runs, datetime.fromisoformat(output_at), now) if output_at else None,
            "latest_fire": fire_view(fires.get(job_id)),
        }
    return {"schema_version": "fleet_activity_v1", "generated_at": iso(now), "snapshot": snapshot_view(snapshot_row, now),
            "outputs_indexed_since": iso(outputs_since), "jobs": jobs, "note": NOTE}
