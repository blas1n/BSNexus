from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src import models
from backend.src.queue.streams import RedisStreamManager
from backend.src.schemas import (
    WorkerPollItem,
    WorkerPollRequest,
    WorkerPollResponse,
    WorkerRegister,
    WorkerResultRequest,
)
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

    # Re-registration: reuse existing worker_id if provided and verify ownership
    if body.worker_id:
        worker_id = body.worker_id
        existing_result = await db.execute(
            select(models.Worker).where(models.Worker.id == uuid.UUID(worker_id))
        )
        existing_worker = existing_result.scalar_one_or_none()
        if existing_worker is None:
            raise HTTPException(status_code=404, detail="Worker not found for re-registration")

        # Verify ownership: the caller must prove they own this worker.
        # 1) If worker_token is provided and still valid in Redis, it must match.
        # 2) If worker_token is expired/missing, the valid registration_token
        #    (already verified above) serves as proof of ownership.
        if body.worker_token:
            resolved_id = await registry.resolve_token(body.worker_token)
            if resolved_id is not None and resolved_id != worker_id:
                raise HTTPException(status_code=403, detail="Worker token does not match worker_id")

        # Invalidate old Redis token before issuing a new one
        await registry.deregister(worker_id)
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
        "poll_interval": 2,
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

    # Throttle DB writes: only update last_heartbeat every 60 seconds
    redis_client = request.app.state.redis
    db_hb_key = f"worker:db_heartbeat:{worker_id}"
    last_db_hb = await redis_client.get(db_hb_key)
    if not last_db_hb:
        await db.execute(
            update(models.Worker)
            .where(models.Worker.id == worker_id)
            .values(last_heartbeat=datetime.now(timezone.utc))
        )
        await db.commit()
        await redis_client.set(db_hb_key, "1", ex=60)

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


# -- Poll / Result endpoints --------------------------------------------------


def _decode_stream_message(data: dict) -> dict:
    """Decode a raw Redis stream message: bytes→str, attempt JSON deserialization."""
    decoded: dict = {}
    for k, v in data.items():
        key = k.decode() if isinstance(k, bytes) else k
        val = v.decode() if isinstance(v, bytes) else v
        try:
            decoded[key] = json.loads(val)
        except (json.JSONDecodeError, TypeError, ValueError):
            decoded[key] = val
    return decoded


async def _xreadgroup_raw(
    redis_client: object,
    stream: str,
    group: str,
    consumer: str,
    start_id: str,
    count: int,
    block: int | None = None,
) -> list[tuple[str, dict]]:
    """Low-level xreadgroup wrapper returning (message_id, decoded_data) pairs."""
    kwargs: dict = {
        "groupname": group,
        "consumername": consumer,
        "streams": {stream: start_id},
        "count": count,
    }
    if block is not None:
        kwargs["block"] = block

    try:
        messages = await redis_client.xreadgroup(**kwargs)  # type: ignore[union-attr]
    except Exception:
        # Stream or consumer group may not exist yet
        return []
    results: list[tuple[str, dict]] = []
    if messages:
        for _stream_name, entries in messages:
            for msg_id, data in entries:
                mid = msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id)
                results.append((mid, _decode_stream_message(data)))
    return results


# Stream key → (Redis stream name, consumer group name)
_STREAM_MAP: dict[str, tuple[str, str]] = {
    "task": (RedisStreamManager.TASKS_QUEUE, RedisStreamManager.GROUP_WORKERS),
    "qa": (RedisStreamManager.TASKS_QA, RedisStreamManager.GROUP_REVIEWERS),
}


@router.post("/{worker_id}/poll")
async def poll_work(
    worker_id: uuid.UUID,
    body: WorkerPollRequest,
    request: Request,
    authenticated_worker_id: str = Depends(verify_worker_token),
) -> WorkerPollResponse:
    """Poll for available work items on behalf of a worker.

    Checks pending (unacknowledged) messages first, then new messages.
    Blocks up to 5 seconds waiting for new work if no pending items exist.
    """
    if str(worker_id) != authenticated_worker_id:
        raise HTTPException(status_code=403, detail="Token does not match worker")

    redis_client = request.app.state.redis
    worker_id_str = str(worker_id)
    items: list[WorkerPollItem] = []

    # Resolve requested poll types to (stream, group, source_label)
    stream_configs: list[tuple[str, str, str]] = []
    for poll_type in body.poll_types:
        if poll_type in _STREAM_MAP:
            stream_name, group_name = _STREAM_MAP[poll_type]
            stream_configs.append((stream_name, group_name, poll_type))

    # Phase 1: Recover pending messages (xreadgroup with "0")
    for stream, group, source in stream_configs:
        pending = await _xreadgroup_raw(redis_client, stream, group, worker_id_str, "0", count=5)
        for msg_id, data in pending:
            # QA messages are routed to a specific reviewer — skip if not assigned to this worker
            if source == "qa" and data.get("reviewer_id") != worker_id_str:
                continue
            items.append(WorkerPollItem(
                type=data.get("type", source),
                message_id=msg_id,
                stream=source,
                data=data,
            ))

    # Phase 2: If no pending, poll for new messages (blocking up to 5s)
    if not items:
        for stream, group, source in stream_configs:
            new_msgs = await _xreadgroup_raw(
                redis_client, stream, group, worker_id_str, ">", count=1, block=5000,
            )
            for msg_id, data in new_msgs:
                # QA messages are routed to a specific reviewer — skip if not assigned to this worker
                if source == "qa" and data.get("reviewer_id") != worker_id_str:
                    continue
                items.append(WorkerPollItem(
                    type=data.get("type", source),
                    message_id=msg_id,
                    stream=source,
                    data=data,
                ))
            if items:
                break  # Return as soon as we have work

    return WorkerPollResponse(items=items)


@router.post("/{worker_id}/result")
async def submit_result(
    worker_id: uuid.UUID,
    body: WorkerResultRequest,
    request: Request,
    authenticated_worker_id: str = Depends(verify_worker_token),
) -> dict:
    """Submit a task/QA/revert result. Publishes to tasks:results and ACKs the original message."""
    if str(worker_id) != authenticated_worker_id:
        raise HTTPException(status_code=403, detail="Token does not match worker")

    stream_manager: RedisStreamManager = request.app.state.stream_manager
    worker_id_str = str(worker_id)

    # Publish result to tasks:results (except for reverts which only need ACK)
    if body.result_type == "execution":
        await stream_manager.publish(RedisStreamManager.TASKS_RESULTS, {
            "task_id": body.task_id,
            "worker_id": worker_id_str,
            "type": "execution",
            "success": str(body.success).lower(),
            "output_path": body.output_path,
            "error_message": body.error_message,
            "error_category": body.error_category,
            "commit_hash": body.commit_hash,
            "branch_name": body.branch_name,
        })
    elif body.result_type == "qa":
        await stream_manager.publish(RedisStreamManager.TASKS_RESULTS, {
            "task_id": body.task_id,
            "worker_id": worker_id_str,
            "type": "qa",
            "passed": str(body.passed).lower(),
            "feedback": body.feedback,
            "error_message": body.error_message,
            "error_category": body.error_category,
            "commit_hash": body.commit_hash,
        })

    # ACK the original message on the source stream
    if body.stream in _STREAM_MAP:
        stream_name, group_name = _STREAM_MAP[body.stream]
        await stream_manager.acknowledge(stream_name, group_name, body.message_id)

    return {"acknowledged": True}
