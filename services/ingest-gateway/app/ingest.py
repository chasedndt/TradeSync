import os
import json
import uuid
import asyncpg
from datetime import datetime
from typing import Optional
from .models.market import MarketSnapshot
from .models.event import NormalizedEvent

# Env vars
PG_DSN = os.getenv("PG_DSN", "postgresql://tradesync:CHANGE_ME@localhost:5432/tradesync")

async def ingest_market_snapshot(snapshot: MarketSnapshot):
    """
    Converts a MarketSnapshot into a NormalizedEvent and inserts it into the database.
    """
    ts = datetime.now()
    event_id = str(uuid.uuid4())
    
    # Provenance data
    provenance = {
        "ip": "127.0.0.1",
        "kind": "internal_collector",
        "received_at": ts.isoformat()
    }

    # Create NormalizedEvent
    # Hash based on source:symbol:ts to ensure uniqueness for this snapshot time
    event_hash = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{snapshot.source}:{snapshot.symbol}:{ts.isoformat()}"))
    
    normalized_event = NormalizedEvent(
        id=event_id,
        ts=ts,
        source=snapshot.source,
        kind="market_snapshot",
        symbol=snapshot.symbol,
        timeframe="1m", # Defaulting to 1m for snapshots, or could be 'realtime'
        payload=snapshot.model_dump(),
        provenance=provenance,
        hash=event_hash
    )

    try:
        conn = await asyncpg.connect(PG_DSN)
        await conn.execute("""
            INSERT INTO events (id, ts, source, kind, symbol, timeframe, payload, provenance, hash)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """, 
            normalized_event.id, 
            normalized_event.ts, 
            normalized_event.source, 
            normalized_event.kind, 
            normalized_event.symbol, 
            normalized_event.timeframe, 
            json.dumps(normalized_event.payload), 
            json.dumps(normalized_event.provenance),
            normalized_event.hash
        )
        await conn.close()
        print(f"Ingested snapshot for {snapshot.symbol} from {snapshot.source}")
    except Exception as e:
        print(f"Error ingesting snapshot: {e}")
