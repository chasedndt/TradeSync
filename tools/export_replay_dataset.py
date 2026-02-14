#!/usr/bin/env python3
"""
Dataset exporter for TradeSync replay engine.

Exports events, signals, and opportunities from Postgres into JSONL files
that the backtest-runner can replay through tradesync_core scoring + risk logic.

Usage:
    python tools/export_replay_dataset.py \
        --name my_dataset \
        --symbols BTC,ETH \
        --hours 24 \
        --pg-dsn postgresql://tradesync:pass@localhost:5432/tradesync

    # Or use PG_DSN env var:
    PG_DSN=postgresql://... python tools/export_replay_dataset.py --name btc_week --symbols BTC --start 2025-01-01 --end 2025-01-07
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


async def export_dataset(
    pg_dsn: str,
    name: str,
    symbols: list[str],
    start: datetime,
    end: datetime,
    output_dir: Path,
):
    import asyncpg

    conn = await asyncpg.connect(pg_dsn)
    try:
        dataset_dir = output_dir / name
        dataset_dir.mkdir(parents=True, exist_ok=True)

        # Normalize symbols to include -PERP variants
        symbol_variants = []
        for s in symbols:
            symbol_variants.append(s)
            if not s.endswith("-PERP"):
                symbol_variants.append(f"{s}-PERP")

        # Export events (canonical CoreEvent schema: ts, source, kind, payload)
        events_rows = await conn.fetch(
            """
            SELECT ts, source, kind, payload, symbol
            FROM events
            WHERE symbol = ANY($1)
              AND ts >= $2 AND ts <= $3
            ORDER BY ts ASC
            """,
            symbol_variants, start, end,
        )

        events_path = dataset_dir / "events.jsonl"
        with open(events_path, "w") as f:
            for r in events_rows:
                payload = r["payload"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                record = {
                    "ts": r["ts"].isoformat(),
                    "source": r["source"],
                    "kind": r["kind"],
                    "payload": payload,
                    "symbol": r["symbol"],
                }
                f.write(json.dumps(record) + "\n")

        # Export signals
        signals_rows = await conn.fetch(
            """
            SELECT id, agent, symbol, timeframe, kind, confidence, dir, features, created_at
            FROM signals
            WHERE symbol = ANY($1)
              AND created_at >= $2 AND created_at <= $3
            ORDER BY created_at ASC
            """,
            symbol_variants, start, end,
        )

        signals_path = dataset_dir / "signals.jsonl"
        with open(signals_path, "w") as f:
            for r in signals_rows:
                features = r["features"]
                if isinstance(features, str):
                    features = json.loads(features)
                record = {
                    "id": str(r["id"]),
                    "agent": r["agent"],
                    "symbol": r["symbol"],
                    "timeframe": r["timeframe"],
                    "kind": r["kind"],
                    "confidence": float(r["confidence"]),
                    "dir": r["dir"],
                    "features": features,
                    "created_at": r["created_at"].isoformat(),
                }
                f.write(json.dumps(record) + "\n")

        # Export opportunities
        opps_rows = await conn.fetch(
            """
            SELECT id, symbol, timeframe, bias, quality, dir, status, snapshot_ts, links, confluence
            FROM opportunities
            WHERE symbol = ANY($1)
              AND snapshot_ts >= $2 AND snapshot_ts <= $3
            ORDER BY snapshot_ts ASC
            """,
            symbol_variants, start, end,
        )

        opps_path = dataset_dir / "opportunities.jsonl"
        with open(opps_path, "w") as f:
            for r in opps_rows:
                links = r["links"]
                if isinstance(links, str):
                    links = json.loads(links)
                confluence = r["confluence"]
                if isinstance(confluence, str):
                    confluence = json.loads(confluence)
                record = {
                    "id": str(r["id"]),
                    "symbol": r["symbol"],
                    "timeframe": r["timeframe"],
                    "bias": float(r["bias"]),
                    "quality": float(r["quality"]),
                    "dir": r["dir"],
                    "status": r["status"],
                    "snapshot_ts": r["snapshot_ts"].isoformat(),
                    "links": links or {},
                    "confluence": confluence or {},
                }
                f.write(json.dumps(record) + "\n")

        # Write metadata
        metadata = {
            "name": name,
            "symbols": symbols,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "counts": {
                "events": len(events_rows),
                "signals": len(signals_rows),
                "opportunities": len(opps_rows),
            },
        }
        with open(dataset_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        print(f"Exported dataset '{name}' to {dataset_dir}")
        print(f"  Events:        {len(events_rows)}")
        print(f"  Signals:       {len(signals_rows)}")
        print(f"  Opportunities: {len(opps_rows)}")

    finally:
        await conn.close()


def main():
    parser = argparse.ArgumentParser(description="Export TradeSync replay dataset")
    parser.add_argument("--name", required=True, help="Dataset name (creates subdirectory)")
    parser.add_argument("--symbols", required=True, help="Comma-separated symbols (e.g. BTC,ETH)")
    parser.add_argument("--hours", type=int, help="Export last N hours")
    parser.add_argument("--start", help="Start datetime (ISO 8601)")
    parser.add_argument("--end", help="End datetime (ISO 8601)")
    parser.add_argument("--pg-dsn", default=None, help="Postgres DSN (or use PG_DSN env)")
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).parent.parent / "data" / "replay"),
        help="Output base directory",
    )

    args = parser.parse_args()

    pg_dsn = args.pg_dsn or os.getenv("PG_DSN")
    if not pg_dsn:
        print("Error: --pg-dsn or PG_DSN env var required", file=sys.stderr)
        sys.exit(1)

    symbols = [s.strip().upper() for s in args.symbols.split(",")]

    if args.hours:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=args.hours)
    elif args.start and args.end:
        start = datetime.fromisoformat(args.start)
        end = datetime.fromisoformat(args.end)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
    else:
        print("Error: provide --hours or both --start and --end", file=sys.stderr)
        sys.exit(1)

    asyncio.run(export_dataset(
        pg_dsn=pg_dsn,
        name=args.name,
        symbols=symbols,
        start=start,
        end=end,
        output_dir=Path(args.output_dir),
    ))


if __name__ == "__main__":
    main()
