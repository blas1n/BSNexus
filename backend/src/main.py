from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.src.api import projects, tasks, workers
from backend.src.storage.database import init_db, engine
from backend.src.storage.redis_client import get_redis, close_redis
from backend.src.queue.streams import RedisStreamManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage server lifecycle: startup and shutdown."""
    # Startup
    await init_db()
    redis = await get_redis()
    stream_manager = RedisStreamManager(redis)
    await stream_manager.initialize_streams()
    app.state.redis = redis
    app.state.stream_manager = stream_manager

    yield

    # Shutdown
    await close_redis()


app = FastAPI(
    title="BSNexus",
    description="AI-Powered Development Manager",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "0.1.0"}


@app.get("/health/deps")
async def health_deps():
    # Check Redis
    redis_status = "disconnected"
    try:
        redis = await get_redis()
        await redis.ping()  # type: ignore[misc]
        redis_status = "connected"
    except Exception:
        pass

    # Check PostgreSQL
    pg_status = "disconnected"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            pg_status = "connected"
    except Exception:
        pass

    return {
        "redis": redis_status,
        "postgresql": pg_status,
    }


# API routers
app.include_router(tasks.router)
app.include_router(projects.router)
app.include_router(workers.router)
