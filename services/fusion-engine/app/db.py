import asyncpg
import os

PG_DSN = os.getenv("PG_DSN", "postgresql://tradesync:CHANGE_ME@postgres:5432/tradesync")

class Database:
    def __init__(self):
        self.pool: asyncpg.Pool = None

    async def connect(self):
        print("Connecting to Postgres...")
        self.pool = await asyncpg.create_pool(dsn=PG_DSN, min_size=2, max_size=10)

    async def disconnect(self):
        if self.pool:
            await self.pool.close()

    async def insert_opportunity(self, data: dict):
        import json
        query = """
        INSERT INTO opportunities (
            symbol, timeframe, bias, quality, dir, links, signal_id, expires_at, confluence
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, NOW() + INTERVAL '1 second' * $8, $9
        ) ON CONFLICT (signal_id) DO NOTHING
        RETURNING id;
        """
        # Phase 3C: Include confluence with score_breakdown, execution_risk, warnings
        confluence = data.get("confluence", {})

        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                query,
                data["symbol"],
                data["timeframe"],
                float(data["bias"]),
                float(data["quality"]),
                data["dir"],
                json.dumps(data["links"]),
                data["signal_id"],
                int(data["ttl_seconds"]),
                json.dumps(confluence)
            )

db = Database()
