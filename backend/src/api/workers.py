from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.src.queue.streams import RedisStreamManager
from backend.src.schemas import WorkerRegister
from backend.src.utils.worker_registry import WorkerRegistry

router = APIRouter(prefix="/api/workers", tags=["workers"])


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
) -> dict:
    """Register a new worker and return connection metadata."""
    registry = _get_registry(request)

    worker_id = str(uuid.uuid4())
    name = body.name or f"worker-{worker_id[:8]}"
    capabilities = list(body.capabilities.keys()) if body.capabilities else []

    result = await registry.register(
        worker_id=worker_id,
        name=name,
        platform=body.platform,
        capabilities=capabilities,
        executor_type=body.executor_type,
    )

    return {
        "worker_id": result["worker_id"],
        "token": result["token"],
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
) -> dict:
    """Send a heartbeat for the given worker (requires valid token)."""
    if str(worker_id) != authenticated_worker_id:
        raise HTTPException(status_code=403, detail="Token does not match worker")

    registry = _get_registry(request)
    alive = await registry.heartbeat(str(worker_id))
    if not alive:
        raise HTTPException(status_code=404, detail="Worker not found or expired")

    worker = await registry.get_worker(str(worker_id))
    status = worker["status"] if worker else "idle"

    return {
        "status": status,
        "pending_tasks": 0,
    }


@router.get("/")
async def list_workers(request: Request) -> list[dict]:
    """Return all active (non-expired) workers."""
    registry = _get_registry(request)
    return await registry.get_all_workers()


@router.delete("/{worker_id}")
async def deregister_worker(
    worker_id: uuid.UUID,
    request: Request,
) -> dict:
    """Deregister (remove) a worker."""
    registry = _get_registry(request)
    await registry.deregister(str(worker_id))
    return {"detail": "Worker deregistered", "worker_id": str(worker_id)}
