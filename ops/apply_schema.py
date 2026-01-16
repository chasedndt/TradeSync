import asyncio
import asyncpg
import os
import time
from pathlib import Path

# Get DB config from environment or use defaults
DB_USER = os.getenv("POSTGRES_USER", "tradesync")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "CHANGE_ME")
DB_NAME = os.getenv("POSTGRES_DB", "tradesync")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

DSN = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

async def wait_for_db(max_retries=20, delay=2):
    """Wait for database to be ready"""
    for i in range(max_retries):
        try:
            conn = await asyncpg.connect(DSN, timeout=5)
            await conn.close()
            print(f"✓ Database is ready")
            return True
        except Exception as e:
            print(f"Waiting for database... ({i+1}/{max_retries})")
            await asyncio.sleep(delay)
    return False

async def main():
    print(f"Connecting to {DB_HOST}:{DB_PORT}/{DB_NAME} as {DB_USER}...")
    
    # Wait for DB to be ready
    if not await wait_for_db():
        print("❌ Failed to connect to database after retries")
        return 1
    
    try:
        conn = await asyncpg.connect(DSN)
        print("✓ Connected to database")
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        return 1

    try:
        # Find schema.sql relative to this script
        script_dir = Path(__file__).parent
        schema_path = script_dir / "sql" / "schema.sql"
        
        print(f"Reading schema from {schema_path}...")
        with open(schema_path, "r", encoding="utf-8-sig") as f:
            schema_sql = f.read()
            
        print("Applying schema...")
        await conn.execute(schema_sql)
        print("✓ Schema applied successfully")
        return 0
        
    except Exception as e:
        print(f"❌ Error applying schema: {e}")
        return 1
    finally:
        await conn.close()

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
