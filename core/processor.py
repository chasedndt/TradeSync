import asyncio
import asyncpg
import os
import json
from core.scoring import calculate_score

# Env vars
PG_DSN = os.getenv("PG_DSN", "postgresql://tradesync:CHANGE_ME@localhost:5432/tradesync")

async def process_events():
    print("Starting Event Processor...")
    while True:
        try:
            conn = await asyncpg.connect(PG_DSN)
            
            # Fetch unprocessed events
            # We use meta->>'processed' is null
            rows = await conn.fetch("""
                SELECT id, symbol, timeframe, payload, meta 
                FROM events 
                WHERE meta->>'processed' IS NULL
                LIMIT 10
            """)
            
            if not rows:
                await conn.close()
                await asyncio.sleep(5)
                continue
                
            print(f"Processing {len(rows)} events...")
            
            for row in rows:
                event = dict(row)
                # Parse payload if it's a string (it should be jsonb but asyncpg might return dict or str depending on decoding)
                if isinstance(event['payload'], str):
                    event['payload'] = json.loads(event['payload'])
                
                # Calculate Score
                opps = calculate_score(event)
                
                # Insert Opportunities
                for opp in opps:
                    await conn.execute("""
                        INSERT INTO opportunities (id, symbol, timeframe, snapshot_ts, bias, quality, dir, confluence, status)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    """, opp['id'], opp['symbol'], opp['timeframe'], opp['snapshot_ts'], opp['bias'], opp['quality'], opp['dir'], json.dumps(opp['confluence']), opp['status'])
                    print(f"Created Opportunity: {opp['id']}")
                
                # Mark event as processed
                # We need to merge 'processed': true into meta
                meta = json.loads(row['meta']) if isinstance(row['meta'], str) else row['meta']
                meta['processed'] = True
                meta['processed_at'] = str(asyncio.get_event_loop().time())
                
                await conn.execute("""
                    UPDATE events SET meta = $1 WHERE id = $2
                """, json.dumps(meta), row['id'])
                
            await conn.close()
            
        except Exception as e:
            print(f"Processor Error: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(process_events())
