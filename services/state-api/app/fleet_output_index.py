"""Each Hermes job's recent stored outputs, found without reading every stored output on every request.

The output bridge files every non-silent job output in quarantine as source
``chaseos``, with the job id inside the stored payload. Finding each job's newest
output that way means reading every stored payload (0.4 s for 770 outputs on
15 September, and growing every day). The index reads the last ``INITIAL_DAYS``
once, then only rows received since the newest it has seen (with an overlap, so
a late commit is not missed), keeps each job's newest ``KEEP_PER_JOB`` output
ids, and reads the full payload only of each job's newest output.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from app.fleet_activity_view import output_summary

INITIAL_DAYS = 8
KEEP_PER_JOB = 10
MIN_REFRESH_S = 15.0
OVERLAP = timedelta(minutes=5)

IDS_SQL = """
SELECT id, received_at, payload->>'job_id' AS job_id FROM quarantine_intake
WHERE source = 'chaseos' AND received_at > $1 AND payload->>'kind' = 'hermes_job_output'
ORDER BY received_at
"""
DETAIL_SQL = "SELECT id, accepted, reasons, observed_at, received_at, payload FROM quarantine_intake WHERE id = ANY($1::uuid[])"


class OutputIndex:
    def __init__(self) -> None:
        self.ids: dict[str, list[tuple[datetime, str]]] = {}
        self.latest: dict[str, dict[str, Any]] = {}
        self.since: datetime | None = None
        self._recent: dict[str, datetime] = {}
        self._watermark: datetime | None = None
        self._refreshed = float("-inf")
        self._lock = asyncio.Lock()

    async def refresh(self, conn, now: datetime | None = None, force: bool = False) -> None:
        async with self._lock:
            if not force and time.monotonic() - self._refreshed < MIN_REFRESH_S:
                return
            now = now or datetime.now(timezone.utc)
            if self._watermark is None:
                self.since = now - timedelta(days=INITIAL_DAYS)
            start = self._watermark - OVERLAP if self._watermark else self.since
            changed: set[str] = set()
            for row in await conn.fetch(IDS_SQL, start):
                output_id, received_at, job_id = str(row["id"]), row["received_at"], row["job_id"]
                self._watermark = max(self._watermark or received_at, received_at)
                if output_id in self._recent or not job_id:
                    continue
                self._recent[output_id] = received_at
                entries = self.ids.setdefault(job_id, [])
                entries.append((received_at, output_id))
                entries.sort(reverse=True)
                del entries[KEEP_PER_JOB:]
                changed.add(job_id)
            if self._watermark:
                self._recent = {k: v for k, v in self._recent.items() if v > self._watermark - 2 * OVERLAP}
            wanted = {self.ids[job][0][1]: job for job in changed if self.latest.get(job, {}).get("id") != self.ids[job][0][1]}
            if wanted:
                for row in await conn.fetch(DETAIL_SQL, list(wanted)):
                    self.latest[wanted[str(row["id"])]] = output_summary(row)
            self._refreshed = time.monotonic()

    def outputs_for(self, job_id: str) -> list[dict[str, Any]]:
        return [{"id": output_id, "received_at": received_at.astimezone(timezone.utc).isoformat()}
                for received_at, output_id in self.ids.get(job_id, [])]


INDEX = OutputIndex()
