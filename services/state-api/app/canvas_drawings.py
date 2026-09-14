"""Market Canvas drawings: the operator's annotations, versioned server-side.

Moved out of ``app/main.py`` unchanged. Validation lives in
``tradesync_core.canvas_drawings``; this module stores and reads versions. A
drawing is annotation: it carries no scoring, approval or execution authority.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tradesync_core import normalize_symbol
from tradesync_core.canvas_drawings import (
    DrawingError,
    next_version,
    validate_drawing,
)

router = APIRouter()

# The app's shared state, bound by register(). Endpoints read ``state.pool`` at
# request time, so the pool created at startup (or patched in a test) is used.
state: Any = None


def register(app, app_state) -> None:
    global state
    state = app_state
    app.include_router(router)



class DrawingPayload(BaseModel):
    """One operator drawing. Annotation only; confers no authority."""

    symbol: str
    interval: str
    kind: str
    points: List[Dict[str, Any]]
    label: str = ""
    colour: str = ""


@router.get("/state/canvas/drawings", tags=["canvas"])
async def list_drawings(symbol: str, interval: str):
    """Current drawings for one chart: each drawing at its live version."""
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")
    resolved = normalize_symbol(symbol)
    try:
        async with state.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT drawing_id, version, kind, points, label, colour, created_at
                FROM canvas_drawings
                WHERE symbol = $1 AND interval = $2
                  AND superseded_at IS NULL AND deleted = false
                ORDER BY created_at
                """,
                resolved,
                interval,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "schema_version": "canvas_drawing_v1",
        "symbol": resolved,
        "interval": interval,
        "authority": "none",
        "drawings": [
            {
                "drawing_id": str(r["drawing_id"]),
                "version": r["version"],
                "kind": r["kind"],
                "points": json.loads(r["points"]) if isinstance(r["points"], str) else r["points"],
                "label": r["label"],
                "colour": r["colour"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ],
    }


async def _insert_drawing_version(conn, drawing, drawing_id, version, deleted=False):
    """Insert one version. Callers supersede the previous row first."""
    await conn.execute(
        """
        INSERT INTO canvas_drawings
            (drawing_id, version, symbol, interval, kind, points, label, colour, deleted)
        VALUES ($1::uuid, $2, $3, $4, $5, $6::jsonb, $7, $8, $9)
        """,
        str(drawing_id),
        version,
        drawing.symbol,
        drawing.interval,
        drawing.kind,
        json.dumps([p.to_dict() for p in drawing.points]),
        drawing.label,
        drawing.colour,
        deleted,
    )


@router.post("/state/canvas/drawings", tags=["canvas"])
async def create_drawing(payload: DrawingPayload):
    """Record a new drawing at version 1."""
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")
    body = payload.model_dump()
    body["symbol"] = normalize_symbol(body["symbol"])
    try:
        drawing = validate_drawing(body)
    except DrawingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    drawing_id = uuid.uuid4()
    try:
        async with state.pool.acquire() as conn:
            await _insert_drawing_version(conn, drawing, drawing_id, next_version(None))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {**drawing.to_dict(), "drawing_id": str(drawing_id), "version": 1}


@router.put("/state/canvas/drawings/{drawing_id}", tags=["canvas"])
async def update_drawing(drawing_id: str, payload: DrawingPayload):
    """Supersede a drawing with a new version. The old version is kept."""
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")
    body = payload.model_dump()
    body["symbol"] = normalize_symbol(body["symbol"])
    try:
        drawing = validate_drawing(body)
    except DrawingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        async with state.pool.acquire() as conn:
            async with conn.transaction():
                current = await conn.fetchrow(
                    """
                    SELECT version FROM canvas_drawings
                    WHERE drawing_id = $1::uuid AND superseded_at IS NULL
                    ORDER BY version DESC LIMIT 1
                    """,
                    drawing_id,
                )
                if not current:
                    raise HTTPException(status_code=404, detail="drawing not found")
                await conn.execute(
                    """
                    UPDATE canvas_drawings SET superseded_at = now()
                    WHERE drawing_id = $1::uuid AND superseded_at IS NULL
                    """,
                    drawing_id,
                )
                version = next_version(current["version"])
                await _insert_drawing_version(conn, drawing, drawing_id, version)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {**drawing.to_dict(), "drawing_id": drawing_id, "version": version}


@router.delete("/state/canvas/drawings/{drawing_id}", tags=["canvas"])
async def delete_drawing(drawing_id: str):
    """Remove a drawing from the chart. Its history is retained."""
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")
    try:
        async with state.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE canvas_drawings SET superseded_at = now(), deleted = true
                WHERE drawing_id = $1::uuid AND superseded_at IS NULL
                """,
                drawing_id,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if result.endswith(" 0"):
        raise HTTPException(status_code=404, detail="drawing not found")
    return {"drawing_id": drawing_id, "deleted": True, "history_retained": True}


@router.get("/state/canvas/drawings/{drawing_id}/history", tags=["canvas"])
async def drawing_history(drawing_id: str):
    """Every version of one drawing, oldest first."""
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")
    try:
        async with state.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT version, kind, points, label, colour, created_at,
                       superseded_at, deleted
                FROM canvas_drawings WHERE drawing_id = $1::uuid
                ORDER BY version
                """,
                drawing_id,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not rows:
        raise HTTPException(status_code=404, detail="drawing not found")

    return {
        "schema_version": "canvas_drawing_v1",
        "drawing_id": drawing_id,
        "versions": [
            {
                "version": r["version"],
                "kind": r["kind"],
                "points": json.loads(r["points"]) if isinstance(r["points"], str) else r["points"],
                "label": r["label"],
                "colour": r["colour"],
                "created_at": r["created_at"].isoformat(),
                "superseded_at": r["superseded_at"].isoformat() if r["superseded_at"] else None,
                "deleted": r["deleted"],
            }
            for r in rows
        ],
    }
