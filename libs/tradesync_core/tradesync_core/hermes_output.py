"""Turn one Hermes cron job's output file into quarantine material.

The Hermes fleet writes every job run to ``cron/output/<job_id>_<YYYYMMDD_HHMMSS>.txt``
before delivering it anywhere. That file is the exact text a Discord channel
receives, and it exists for the forty-odd jobs that deliver only ``local`` —
including the three StrikeZone full-thesis editions — which never reach
Discord at all. Reading these files is therefore the complete view of the
fleet, and it needs no bot token.

Pure mapping only. The bridge that scans the directory and posts is a host
script (``tools/hermes_output_bridge.py``); this module decides what one file
becomes and is tested without a filesystem.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

SCHEMA_VERSION = "hermes_job_output_v1"
SOURCE = "chaseos"
MAX_CONTENT_CHARS = 48_000  # quarantine bounds the payload at 64 KB
TRUNCATED_NOTE = "[truncated by hermes_output: file exceeded the content bound]"

_FILENAME = re.compile(r"^(?P<job_id>[0-9a-f]{12})_(?P<stamp>\d{8}_\d{6})\.txt$")


@dataclass(frozen=True)
class OutputFile:
    job_id: str
    ran_at_ms: int
    filename: str
    stamp: str = ""


def parse_filename(name: str) -> OutputFile | None:
    """``<job_id>_<YYYYMMDD_HHMMSS>.txt`` -> its parts, or None for anything else.

    The latest-file copies (bare ``<job_id>``) and any other files are ignored
    rather than guessed at. The stamp is the fleet host's local wall clock.
    """
    m = _FILENAME.match(name)
    if not m:
        return None
    try:
        ran = datetime.strptime(m.group("stamp"), "%Y%m%d_%H%M%S")
    except ValueError:
        return None
    return OutputFile(m.group("job_id"), int(ran.replace(tzinfo=timezone.utc).timestamp() * 1000), name, m.group("stamp"))


_MARKDOWN = re.compile(r"^(?P<stamp>\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.md$")
_JOB_DIR = re.compile(r"^[0-9a-f]{12}$")


def parse_markdown_run(job_dir_name: str, name: str) -> OutputFile | None:
    """``cron/output/<job_id>/<YYYY-MM-DD_HH-MM-SS>.md`` -> its parts, or None.

    Some jobs write a dated markdown per run inside a per-job directory as
    well as (or instead of) the flat text capture. Where both exist the
    markdown is the richer artifact, and the bridge prefers it.
    """
    if not _JOB_DIR.match(job_dir_name):
        return None
    m = _MARKDOWN.match(name)
    if not m:
        return None
    try:
        ran = datetime.strptime(m.group("stamp"), "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return None
    return OutputFile(job_dir_name, int(ran.replace(tzinfo=timezone.utc).timestamp() * 1000), f"{job_dir_name}/{name}", m.group("stamp"))


_SILENT = re.compile(r"\*\*Status:\*\*\s*silent \(empty output\)", re.IGNORECASE)


def is_silent(content: str) -> bool:
    """A run the fleet itself marked as having produced nothing.

    Script jobs that found nothing to do write a stub saying so. Holding
    those would fill the feed with "nothing happened" at every cadence, so
    the bridge skips them; the fleet's own health inspector already counts
    them.
    """
    return bool(_SILENT.search(content))


def job_label(job: Mapping[str, Any] | None, job_id: str) -> str:
    return str((job or {}).get("name") or f"hermes-job-{job_id}")


def delivery_of(job: Mapping[str, Any] | None, channels: Mapping[str, str]) -> dict[str, Any]:
    """Where the fleet delivered this job: local, origin, or a labelled Discord channel."""
    raw = str((job or {}).get("deliver") or "local")
    if raw.startswith("discord:"):
        channel_id = raw.split(":", 1)[1]
        return {"kind": "discord", "channel_id": channel_id, "channel_label": channels.get(channel_id, channel_id)}
    return {"kind": raw, "channel_id": None, "channel_label": None}


def to_submission(
    output: OutputFile,
    content: str,
    job: Mapping[str, Any] | None,
    channels: Mapping[str, str],
    observed_at_ms: int | None = None,
) -> dict[str, Any]:
    """One output file -> ``{"source", "payload", "observed_at_ms"}``.

    ``observed_at_ms`` defaults to the file's own stamp; callers that know the
    file's modification time should pass it, because the stamp is in the
    fleet host's local time and quarantine judges staleness in UTC.
    """
    truncated = len(content) > MAX_CONTENT_CHARS
    if truncated:
        content = content[:MAX_CONTENT_CHARS] + "\n" + TRUNCATED_NOTE
    schedule = (job or {}).get("schedule") or {}
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "hermes_job_output",
        "agent": job_label(job, output.job_id),
        "job_id": output.job_id,
        "job_enabled": bool((job or {}).get("enabled", True)),
        "schedule": str(schedule.get("display") or "") if isinstance(schedule, Mapping) else str(schedule),
        "delivery": delivery_of(job, channels),
        "ran_at_stamp": output.stamp,
        "content": content,
        "content_truncated": truncated,
        "filename": output.filename,
    }
    return {"source": SOURCE, "payload": payload, "observed_at_ms": observed_at_ms if observed_at_ms is not None else output.ran_at_ms}
