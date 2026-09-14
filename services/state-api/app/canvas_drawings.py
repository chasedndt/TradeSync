"""Market Canvas drawings: the operator's annotations, versioned server-side.

Validation lives in ``tradesync_core.canvas_drawings``; this module stores and
reads versions. Drawings are anchored in absolute time and price, so a symbol's
drawings can be read across every interval, each naming the interval it was
drawn on. A drawing is annotation: it carries no scoring, approval or execution
authority.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

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
    # Any rather than a dict type, so a malformed style is refused by the
    # validator with a reason instead of by request parsing.
    style: Any = None


def _jsonb(value: Any) -> Any:
    """jsonb arrives as text unless a codec is registered; accept either."""
    return json.loads(value) if isinstance(value, str) else value


def _updated_count(status: Any) -> int:
    """asyncpg reports a command as ``UPDATE <n>``; the count is the last word."""
    try:
        return int(str(status).rsplit(" ", 1)[-1])
    except ValueError:
        return 0


@router.get("/state/canvas/drawings", tags=["canvas"])
async def list_drawings(symbol: str, interval: Optional[str] = None, all_intervals: bool = False):
    """Current drawings for one chart: each drawing at its live version.

    With ``all_intervals=true`` every live drawing for the symbol is returned,
    whichever interval it was drawn on, and each names that interval. Without
    it the read is one interval's, as it always was.
    """
    if not all_intervals and not interval:
        raise HTTPException(status_code=422, detail="interval is required unless all_intervals=true")
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")
    resolved = normalize_symbol(symbol)
    try:
        async with state.pool.acquire() as conn:
            if all_intervals:
                rows = await conn.fetch(
                    """
                    SELECT drawing_id, version, interval, kind, points, label, colour, style, created_at
                    FROM canvas_drawings
                    WHERE symbol = $1
                      AND superseded_at IS NULL AND deleted = false
                    ORDER BY created_at
                    """,
                    resolved,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT drawing_id, version, interval, kind, points, label, colour, style, created_at
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
        "all_intervals": all_intervals,
        "authority": "none",
        "drawings": [
            {
                "drawing_id": str(r["drawing_id"]),
                "version": r["version"],
                "interval": r["interval"],
                "kind": r["kind"],
                "points": _jsonb(r["points"]),
                "label": r["label"],
                "colour": r["colour"],
                "style": _jsonb(r["style"]),
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
            (drawing_id, version, symbol, interval, kind, points, label, colour, style, deleted)
        VALUES ($1::uuid, $2, $3, $4, $5, $6::jsonb, $7, $8, $9::jsonb, $10)
        """,
        str(drawing_id),
        version,
        drawing.symbol,
        drawing.interval,
        drawing.kind,
        json.dumps([p.to_dict() for p in drawing.points]),
        drawing.label,
        drawing.colour,
        json.dumps(drawing.style.to_dict()) if drawing.style else None,
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


@router.delete("/state/canvas/drawings", tags=["canvas"])
async def delete_symbol_drawings(symbol: str):
    """Remove every live drawing for a symbol, on every interval. History is retained."""
    if not state.pool:
        raise HTTPException(status_code=503, detail="DB Pool not ready")
    resolved = normalize_symbol(symbol)
    try:
        async with state.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE canvas_drawings SET superseded_at = now(), deleted = true
                WHERE symbol = $1 AND superseded_at IS NULL
                """,
                resolved,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"symbol": resolved, "deleted": _updated_count(result), "history_retained": True}


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
                SELECT version, kind, points, label, colour, style, created_at,
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
                "points": _jsonb(r["points"]),
                "label": r["label"],
                "colour": r["colour"],
                "style": _jsonb(r["style"]),
                "created_at": r["created_at"].isoformat(),
                "superseded_at": r["superseded_at"].isoformat() if r["superseded_at"] else None,
                "deleted": r["deleted"],
            }
            for r in rows
        ],
    }
