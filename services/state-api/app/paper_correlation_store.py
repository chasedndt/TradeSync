"""Stored correlation measurements. Entry admission reads the latest; it never fetches under the lock."""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.paper_json import decode


async def latest(conn) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        "SELECT measured_at, bar_interval, window_bars, symbols, matrix, overlaps, unmeasured, source "
        "FROM paper_correlation_measurements ORDER BY measured_at DESC LIMIT 1"
    )
    if row is None:
        return None
    return {**dict(row), **{key: decode(row[key]) for key in ("symbols", "matrix", "overlaps", "unmeasured")}}


async def insert(conn, measurement: dict[str, Any], source: str) -> None:
    await conn.execute(
        "INSERT INTO paper_correlation_measurements (id, bar_interval, window_bars, symbols, matrix, overlaps, unmeasured, source) "
        "VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb, $7::jsonb, $8)",
        uuid.uuid4(), measurement["bar_interval"], measurement["window_bars"], json.dumps(measurement["symbols"]),
        json.dumps(measurement["matrix"]), json.dumps(measurement["overlaps"]), json.dumps(measurement["unmeasured"]), source,
    )


async def prune(conn, keep_days: int = 30) -> None:
    await conn.execute("DELETE FROM paper_correlation_measurements WHERE measured_at < now() - make_interval(days => $1)", keep_days)
