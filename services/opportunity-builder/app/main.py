import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.db import db
from app.redis_client import redis_client

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await db.connect()
    await redis_client.connect()
    
    # Ensure consumer group exists
    from app.worker import STREAM_NAME, GROUP_NAME
    await redis_client.ensure_consumer_group(STREAM_NAME, GROUP_NAME)
    
    # Start background worker
    from app.worker import run_worker
    app.state.worker_task = asyncio.create_task(run_worker())
    
    yield
    # Shutdown
    if hasattr(app.state, "worker_task"):
        app.state.worker_task.cancel()
        try:
            await app.state.worker_task
        except asyncio.CancelledError:
            pass
            
    await db.disconnect()
    await redis_client.disconnect()

app = FastAPI(title="Opportunity Builder", version="0.1.0", lifespan=lifespan)

@app.get("/healthz")
async def healthz():
    return {"ok": True}

@app.get("/stats")
async def get_stats():
    from app.worker import stats
    return stats
