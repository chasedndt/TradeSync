"""Thesis editions: the thesis for every tracked symbol, frozen on a schedule.

Three editions a day, on the StrikeZone cadence in London time (NY
premarket 12:00, NY midday 17:30, session handoff 23:30), plus a manual
edition on request. Each edition assembles the live thesis for every symbol
through the same gatherer the Thesis page uses, composes the headline, the
written text and the spoken script (``tradesync_core.thesis_edition``), and
stores the lot. Media renderers (narration audio, video) attach to an
edition afterwards; they never generate one.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import BaseModel

from app.thesis import Evidence, _no_evidence, gather_inputs, execution_enabled, CANDLE_BUCKET_S
from tradesync_core.thesis import build_thesis
from tradesync_core.thesis_edition import EDITIONS, compose

router = APIRouter(tags=["thesis"])

# Where the host renderer writes narration and video, mounted read-only.
EDITIONS_DIR = Path(os.getenv("EDITIONS_DIR", "/editions"))


class MediaAttach(BaseModel):
    kind: str
    filename: str

EDITION_TZ = ZoneInfo(os.getenv("THESIS_EDITION_TZ", "Europe/London"))
# "name=HH:MM,..." in EDITION_TZ. The StrikeZone fleet's three editions.
EDITION_SCHEDULE = os.getenv("THESIS_EDITION_SCHEDULE", "ny-premarket=12:00,ny-midday=17:30,session-handoff=23:30")
EDITIONS_ENABLED = os.getenv("THESIS_EDITIONS_ENABLED", "true").strip().lower() == "true"


def parse_schedule(raw: str) -> list[tuple[str, int, int]]:
    out = []
    for entry in (p.strip() for p in raw.split(",") if p.strip()):
        name, _, hhmm = entry.partition("=")
        hh, _, mm = hhmm.partition(":")
        if name in EDITIONS and hh.isdigit() and mm.isdigit():
            out.append((name, int(hh), int(mm)))
    return out


async def tracked_symbols(market_data_url: str) -> list[str]:
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            r = await client.get(f"{market_data_url}/snapshots", timeout=15.0)
            r.raise_for_status()
            return [s["symbol"] for s in r.json().get("snapshots", []) if s.get("venue") == "hyperliquid"]
    except (httpx.HTTPError, ValueError, KeyError):
        return []


async def build_edition(pool, market_data_url: str, calendar, evidence: Evidence, edition: str, trigger: str) -> dict[str, Any]:
    symbols = await tracked_symbols(market_data_url)
    if not symbols:
        raise HTTPException(status_code=503, detail="no tracked symbols from market-data")
    now = datetime.now(timezone.utc)
    theses: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        inputs = await gather_inputs(pool, symbol, market_data_url, calendar, evidence)
        theses[symbol] = build_thesis(
            symbol=symbol, now_ms=int(time.time() * 1000), regime=inputs["regime"], signal=inputs["signal"],
            source_status=inputs["source_status"], observation_age_ms=inputs["observation_age_ms"],
            candles=inputs["candles"], bucket_s=CANDLE_BUCKET_S, contributors=inputs["contributors"],
            cards=inputs["cards"], gate=inputs["gate"], events=inputs["events"],
            execution_enabled=execution_enabled(), feature_results=inputs["feature_results"], sources=inputs["sources"],
        )
    composed = compose(edition, now, theses, symbols)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO thesis_editions (edition, generated_at, symbols, theses, headline, text, narration, verdicts, trigger)
            VALUES ($1, $2, $3::jsonb, $4::jsonb, $5, $6, $7, $8::jsonb, $9) RETURNING id
            """,
            edition, now, json.dumps(composed["symbols"]), json.dumps(theses), composed["headline"],
            composed["text"], composed["narration"], json.dumps(composed["verdicts"]), trigger,
        )
    return {**composed, "id": str(row["id"]), "trigger": trigger}


def _row_to_edition(r, with_theses: bool) -> dict[str, Any]:
    out = {
        "id": str(r["id"]), "edition": r["edition"], "generated_at": r["generated_at"].isoformat(),
        "symbols": r["symbols"] if not isinstance(r["symbols"], str) else json.loads(r["symbols"]),
        "headline": r["headline"], "text": r["text"], "narration": r["narration"],
        "verdicts": r["verdicts"] if not isinstance(r["verdicts"], str) else json.loads(r["verdicts"]),
        "media": r["media"] if not isinstance(r["media"], str) else json.loads(r["media"]),
        "trigger": r["trigger"], "schema_version": r["schema_version"],
    }
    if with_theses:
        out["theses"] = r["theses"] if not isinstance(r["theses"], str) else json.loads(r["theses"])
    return out


def next_fire(now: datetime, schedule: list[tuple[str, int, int]]) -> tuple[str, datetime]:
    local = now.astimezone(EDITION_TZ)
    candidates = []
    for name, hh, mm in schedule:
        at = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if at <= local:
            at += timedelta(days=1)
        candidates.append((at, name))
    at, name = min(candidates)
    return name, at.astimezone(timezone.utc)


def register(app, state, *, market_data_url: str, calendar: Callable[[], Awaitable[dict[str, Any]]], evidence: Evidence = _no_evidence) -> None:
    @router.get("/state/thesis/editions")
    async def list_editions(limit: int = Query(10, ge=1, le=50)):
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        async with state.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM thesis_editions ORDER BY generated_at DESC LIMIT $1", limit)
        name, at = next_fire(datetime.now(timezone.utc), parse_schedule(EDITION_SCHEDULE)) if parse_schedule(EDITION_SCHEDULE) else (None, None)
        return {"schema_version": "thesis_editions_v1", "editions": [_row_to_edition(r, False) for r in rows],
                "schedule": {"timezone": str(EDITION_TZ), "entries": EDITION_SCHEDULE, "enabled": EDITIONS_ENABLED,
                             "next": {"edition": name, "at": at.isoformat() if at else None}}}

    @router.get("/state/thesis/editions/{edition_id}")
    async def get_edition(edition_id: str):
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        async with state.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM thesis_editions WHERE id = $1::uuid", edition_id)
        if not row:
            raise HTTPException(status_code=404, detail="no such edition")
        return _row_to_edition(row, True)

    @router.post("/state/thesis/editions/{edition_id}/media")
    async def attach_media(edition_id: str, body: MediaAttach):
        """The host renderer says which file it produced for an edition.

        Files live under EDITIONS_DIR/<edition_id>/ on a read-only mount; only
        a bare filename is recorded, so nothing outside that directory can be
        referenced.
        """
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        if body.kind not in ("audio", "video", "subtitles", "slides") or "/" in body.filename or "\\" in body.filename or ".." in body.filename:
            raise HTTPException(status_code=400, detail="kind must be audio|video|subtitles|slides and filename a bare name")
        async with state.pool.acquire() as conn:
            n = await conn.execute(
                "UPDATE thesis_editions SET media = media || $2::jsonb WHERE id = $1::uuid",
                edition_id, json.dumps({body.kind: body.filename}),
            )
        if not n.endswith("1"):
            raise HTTPException(status_code=404, detail="no such edition")
        return {"id": edition_id, "attached": {body.kind: body.filename}}

    @router.get("/state/thesis/editions/{edition_id}/media/{filename}")
    async def serve_media(edition_id: str, filename: str):
        if "/" in filename or "\\" in filename or ".." in filename or ".." in edition_id or "/" in edition_id:
            raise HTTPException(status_code=400, detail="bare names only")
        path = EDITIONS_DIR / edition_id / filename
        if not path.is_file():
            raise HTTPException(status_code=404, detail="no such media file")
        media_type = {".mp3": "audio/mpeg", ".mp4": "video/mp4", ".srt": "text/plain", ".png": "image/png"}.get(path.suffix.lower(), "application/octet-stream")
        return FileResponse(str(path), media_type=media_type, filename=filename)

    @router.post("/state/thesis/editions/generate")
    async def generate(edition: str = Query("manual")):
        if edition not in EDITIONS:
            raise HTTPException(status_code=400, detail=f"edition must be one of {', '.join(EDITIONS)}")
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        return await build_edition(state.pool, market_data_url, calendar, evidence, edition, "operator")

    async def scheduler():
        schedule = parse_schedule(EDITION_SCHEDULE)
        if not EDITIONS_ENABLED or not schedule:
            return
        while True:
            name, at = next_fire(datetime.now(timezone.utc), schedule)
            await asyncio.sleep(max(1.0, (at - datetime.now(timezone.utc)).total_seconds()))
            try:
                if state.pool:
                    await build_edition(state.pool, market_data_url, calendar, evidence, name, "schedule")
            except Exception as exc:  # the next edition must still fire
                print(f"[Editions] {name} failed: {type(exc).__name__}: {exc}")
            await asyncio.sleep(61)

    @app.on_event("startup")
    async def _start_editions():
        asyncio.create_task(scheduler())

    app.include_router(router)
