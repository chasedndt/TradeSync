"""Record each candidate feature's entry reading for opportunities the job reviews.

Runs inside the outcome job's pass, after outcomes and regimes. For every
opportunity that has no entry-feature rows yet, the feature's stored series is
read from ``market-data`` and the newest sample before entry, within the
feature's freshness tolerance, is written once (``tradesync_core.entry_features``).

The store keeps seven days. An opportunity older than that gets an explicit
"history expired" row for every feature rather than being retried forever, so
the backlog is finite and the evidence cards can count what was never
recordable.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

from tradesync_core.entry_features import (
    SCHEMA_VERSION,
    EntryReading,
    candidate_features,
    reading_at_entry,
    tolerance_ms,
)

MARKET_DATA_URL = os.getenv("MARKET_DATA_URL", "http://market-data:8005")
# The store's retention, less a margin so a series read near the boundary is
# not silently truncated at its old end.
HISTORY_RETENTION_S = int(os.getenv("FEATURE_HISTORY_RETENTION_S", str(6 * 24 * 3600)))
EXPIRED = "feature history no longer covers this entry time"
UNAVAILABLE = "feature history could not be read on this pass"


def _catalog_path() -> Path:
    configured = os.getenv("MARKET_FEATURE_CATALOG_PATH")
    if configured:
        return Path(configured)
    relative = "config/features/market-feature-catalog-v1.json"
    # Repository checkout (services/core-scorer/app -> repo root) or the
    # container, where the catalog is copied to /app/config.
    here = Path(__file__).resolve()
    roots = [here.parents[i] for i in range(min(4, len(here.parents)))] + [Path("/app")]
    for root in roots:
        candidate = root / relative
        if candidate.exists():
            return candidate
    raise FileNotFoundError("market feature catalog not found")


def load_candidates() -> tuple[str, dict[str, dict[str, Any]]]:
    """Catalog version and the specs of every feature that can be tested."""
    data = json.loads(_catalog_path().read_text(encoding="utf-8"))
    features = data["features"]
    return str(data["version"]), {f: features[f] for f in candidate_features(features)}


async def missing_feature_opportunities(conn, batch: int) -> list[dict[str, Any]]:
    """Opportunities with a direction but no entry-feature rows at all, oldest first."""
    rows = await conn.fetch(
        """
        SELECT o.id, o.symbol, o.snapshot_ts
        FROM opportunities o
        WHERE o.dir IN ('LONG', 'SHORT')
          AND NOT EXISTS (
            SELECT 1 FROM opportunity_entry_features f WHERE f.opportunity_id = o.id
          )
        ORDER BY o.snapshot_ts ASC
        LIMIT $1
        """,
        batch,
    )
    return [dict(r) for r in rows]


async def fetch_series(
    client: httpx.AsyncClient, symbol: str, feature_id: str
) -> list[dict[str, Any]] | None:
    """The feature's stored series, or None when it could not be read."""
    try:
        response = await client.get(
            f"{MARKET_DATA_URL}/feature-history/hyperliquid/{symbol}/{feature_id}",
            params={"window": "7d"},
            timeout=20.0,
        )
        response.raise_for_status()
        data = response.json().get("data")
        return data if isinstance(data, list) else []
    except (httpx.HTTPError, ValueError) as exc:
        print(f"[EntryFeatures] history unavailable for {symbol} {feature_id}: {exc}")
        return None


async def store_reading(
    conn, opportunity_id: str, symbol: str, spec: dict[str, Any], catalog_version: str, reading
) -> None:
    await conn.execute(
        """
        INSERT INTO opportunity_entry_features (
            opportunity_id, feature_id, symbol, value, unit, observed_at, age_ms,
            provenance, source_authority, scoring_eligible_at_entry, catalog_version,
            reason, schema_version
        ) VALUES (
            $1::uuid, $2, $3, $4, $5, to_timestamp($6::double precision / 1000.0), $7,
            $8, $9, $10, $11, $12, $13
        )
        ON CONFLICT (opportunity_id, feature_id) DO NOTHING
        """,
        opportunity_id,
        reading.feature_id,
        symbol,
        reading.value,
        str(spec.get("unit", "")),
        reading.observed_at_ms,
        reading.age_ms,
        str(spec.get("provenance", "")),
        str(spec.get("source_authority", "")),
        bool(spec.get("scoring_eligible", False)),
        catalog_version,
        reading.reason,
        SCHEMA_VERSION,
    )


async def record_entry_features(conn, batch: int, now_s: int) -> dict[str, int]:
    """One pass: read series once per (symbol, feature) and label the batch.

    Returns counts of readings written with a value, written as absent, and
    opportunities left for a later pass because history could not be read.
    """
    rows = await missing_feature_opportunities(conn, batch)
    if not rows:
        return {"present": 0, "absent": 0, "deferred": 0}
    version, specs = load_candidates()
    counts = {"present": 0, "absent": 0, "deferred": 0}
    series: dict[tuple[str, str], list[dict[str, Any]] | None] = {}

    async with httpx.AsyncClient() as client:
        for row in rows:
            symbol = row["symbol"]
            opened_ms = int(row["snapshot_ts"].timestamp() * 1000)
            expired = opened_ms < (now_s - HISTORY_RETENTION_S) * 1000
            deferred = False
            readings = []
            for feature_id, spec in specs.items():
                if expired:
                    readings.append(EntryReading(feature_id, None, None, None, EXPIRED))
                    continue
                key = (symbol, feature_id)
                if key not in series:
                    series[key] = await fetch_series(client, symbol, feature_id)
                points = series[key]
                if points is None:
                    deferred = True
                    break
                readings.append(reading_at_entry(feature_id, points, opened_ms, tolerance_ms(spec)))
            if deferred:
                # Write nothing for this opportunity: a partial set would make
                # it look complete to the "no rows yet" query.
                counts["deferred"] += 1
                continue
            for reading in readings:
                await store_reading(conn, str(row["id"]), symbol, specs[reading.feature_id], version, reading)
                counts["present" if reading.present else "absent"] += 1
    return counts
