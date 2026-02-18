from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src import models
from backend.src.queue.streams import RedisStreamManager
from backend.src.schemas import WorkerRegister
from backend.src.storage.database import get_db
from backend.src.utils.worker_registry import WorkerRegistry
from fastapi import APIRouter, Depends, HTTPException, Request

router = APIRouter(prefix="/api/v1/workers", tags=["workers"])


# -- Dependency helpers --------------------------------------------------------


def _get_registry(request: Request) -> WorkerRegistry:
    """Build a WorkerRegistry from the app-level Redis client."""
    return WorkerRegistry(request.app.state.redis)


# -- Auth dependency -----------------------------------------------------------


async def verify_worker_token(request: Request) -> str:
    """Validate ``Authorization: Bearer {token}`` and return the worker_id."""
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")

    token = auth.split(" ", 1)[1]
    registry = _get_registry(request)
    worker_id = await registry.resolve_token(token)
    if not worker_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    return worker_id


# -- Endpoints ----------------------------------------------------------------


@router.post("/register")
async def register_worker(
    body: WorkerRegister,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Register a new worker and return connection metadata.

    Requires a valid registration token created via the admin UI.
    """
    # Validate registration token
    result = await db.execute(
        select(models.RegistrationToken).where(models.RegistrationToken.token == body.registration_token)
    )
    reg_token = result.scalar_one_or_none()

    if not reg_token:
        raise HTTPException(status_code=401, detail="Invalid registration token")
    if reg_token.revoked:
        raise HTTPException(status_code=401, detail="Registration token has been revoked")
    if reg_token.expires_at and reg_token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Registration token has expired")

    # Proceed with Redis-based worker registration
    registry = _get_registry(request)

    # Re-registration: reuse existing worker_id if provided
    if body.worker_id:
        worker_id = body.worker_id
    else:
        worker_id = str(uuid.uuid4())

    name = body.name or f"worker-{worker_id[:8]}"
    capabilities = list(body.capabilities.keys()) if body.capabilities else []

    reg_result = await registry.register(
        worker_id=worker_id,
        name=name,
        platform=body.platform,
        capabilities=capabilities,
        executor_type=body.executor_type,
    )

    # Upsert worker in DB for persistent storage
    now = datetime.now(timezone.utc)
    worker_uuid = uuid.UUID(worker_id)
    existing = await db.execute(select(models.Worker).where(models.Worker.id == worker_uuid))
    db_worker = existing.scalar_one_or_none()

    if db_worker:
        db_worker.name = name
        db_worker.platform = body.platform
        db_worker.capabilities = capabilities
        db_worker.executor_type = body.executor_type
        db_worker.status = models.WorkerStatus.idle
        db_worker.last_heartbeat = now
    else:
        db_worker = models.Worker(
            id=worker_uuid,
            name=name,
            platform=body.platform,
            capabilities=capabilities,
            executor_type=body.executor_type,
            status=models.WorkerStatus.idle,
            registered_at=now,
            last_heartbeat=now,
        )
        db.add(db_worker)

    await db.commit()

    return {
        "worker_id": reg_result["worker_id"],
        "token": reg_result["token"],
        "heartbeat_interval": 30,
        "streams": {
            "tasks_queue": RedisStreamManager.TASKS_QUEUE,
            "tasks_results": RedisStreamManager.TASKS_RESULTS,
            "tasks_qa": RedisStreamManager.TASKS_QA,
        },
        "consumer_groups": {
            "workers": RedisStreamManager.GROUP_WORKERS,
            "reviewers": RedisStreamManager.GROUP_REVIEWERS,
        },
    }


@router.post("/{worker_id}/heartbeat")
async def heartbeat_worker(
    worker_id: uuid.UUID,
    request: Request,
    authenticated_worker_id: str = Depends(verify_worker_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Send a heartbeat for the given worker (requires valid token)."""
    if str(worker_id) != authenticated_worker_id:
        raise HTTPException(status_code=403, detail="Token does not match worker")

    registry = _get_registry(request)
    alive = await registry.heartbeat(str(worker_id))
    if not alive:
        raise HTTPException(status_code=404, detail="Worker not found or expired")

    # Update DB last_heartbeat
    await db.execute(
        update(models.Worker)
        .where(models.Worker.id == worker_id)
        .values(last_heartbeat=datetime.now(timezone.utc))
    )
    await db.commit()

    worker = await registry.get_worker(str(worker_id))
    status = worker["status"] if worker else "idle"

    return {
        "status": status,
        "pending_tasks": 0,
    }


@router.get("")
async def list_workers(request: Request, db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Return all workers with DB data + Redis real-time status merged."""
    registry = _get_registry(request)

    # Get all workers from DB (persistent data including project_id)
    result = await db.execute(select(models.Worker))
    db_workers = result.scalars().all()

    if not db_workers:
        return []

    # Batch fetch Redis status for all workers
    worker_ids = [str(w.id) for w in db_workers]
    redis_workers = await registry.get_workers_by_ids(worker_ids)
    redis_map = {w["id"]: w for w in redis_workers}

    workers: list[dict] = []
    for w in db_workers:
        redis_data = redis_map.get(str(w.id))
        status = redis_data["status"] if redis_data else "offline"
        current_task_id = (redis_data.get("current_task_id") or None) if redis_data else None

        workers.append({
            "id": str(w.id),
            "name": w.name,
            "platform": w.platform,
            "capabilities": w.capabilities,
            "executor_type": w.executor_type,
            "status": status,
            "current_task_id": current_task_id,
            "project_id": str(w.project_id) if w.project_id else None,
            "registered_at": w.registered_at.isoformat() if w.registered_at else None,
            "last_heartbeat": w.last_heartbeat.isoformat() if w.last_heartbeat else None,
        })

    return workers


@router.delete("/{worker_id}")
async def deregister_worker(
    worker_id: uuid.UUID,
    request: Request,
) -> dict:
    """Deregister (remove) a worker."""
    registry = _get_registry(request)
    await registry.deregister(str(worker_id))
    return {"detail": "Worker deregistered", "worker_id": str(worker_id)}
