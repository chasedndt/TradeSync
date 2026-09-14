"""Bounded live jobs overlay. Usage/history stay bridge-backed; no registry writes."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from app import hermes_jobs
from tradesync_core.job_errors import redact

TTL = 15.0
_cache: dict = {}
_lock = asyncio.Lock()
FIELDS = ('name', 'enabled', 'state', 'deliver', 'schedule', 'last_run_at',
          'last_status', 'next_run_at', 'failure_streak')


def invalidate() -> None:
    _cache.clear()


async def overlay(rows: list[dict]) -> tuple[list[dict], dict]:
    async with _lock:
        if time.monotonic() - _cache.get('at', -TTL) >= TTL:
            try:
                jobs = await asyncio.wait_for(hermes_jobs.list_jobs(), timeout=3)
                _cache.update(at=time.monotonic(), jobs=jobs, ok=True,
                              observed_at=datetime.now(timezone.utc).isoformat())
            except (hermes_jobs.HermesJobsError, TimeoutError, ValueError, KeyError, TypeError):
                _cache.update(at=time.monotonic(), jobs=[], ok=False, observed_at=None)
    meta = {'source': 'gateway' if _cache['ok'] else 'bridge',
            'status': 'live' if _cache['ok'] else 'unavailable',
            'observed_at': _cache['observed_at'], 'cache_seconds': TTL}
    if not _cache['ok']:
        return [{**r, 'state_source': 'bridge'} for r in rows], meta
    live = {str(j.get('id')): j for j in _cache['jobs'] if isinstance(j, dict)}
    out = []
    for row in rows:
        job = live.get(row['job_id'])
        if job is None:
            out.append({**row, 'state_source': 'bridge', 'gateway_missing': True})
            continue
        patch = {k: job[k] for k in FIELDS if k in job}
        for field in ('last_error', 'last_delivery_error'):
            patch[field] = redact(job.get(field))
        patch['schedule_display'] = hermes_jobs.schedule_display(job)
        out.append({**row, **patch, 'state_source': 'gateway'})
    return out, meta
