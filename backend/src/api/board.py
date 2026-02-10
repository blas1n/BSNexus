from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

import redis.asyncio as aioredis

from backend.src import models, schemas
from backend.src.repositories.task_repository import TaskRepository
from backend.src.storage.database import get_db
from backend.src.utils.worker_registry import WorkerRegistry

router = APIRouter(prefix="/api/board", tags=["board"])


def _build_task_response(task: models.Task) -> schemas.TaskResponse:
    """Build TaskResponse from Task ORM object."""
    dep_ids = [dep.id for dep in task.depends_on] if task.depends_on else []
    return schemas.TaskResponse(
        id=task.id,
        project_id=task.project_id,
        phase_id=task.phase_id,
        title=task.title,
        description=task.description,
        status=schemas.TaskStatus(task.status.value),
        priority=schemas.TaskPriority(task.priority.value),
        worker_prompt=task.worker_prompt,
        qa_prompt=task.qa_prompt,
        branch_name=task.branch_name,
        commit_hash=task.commit_hash,
        worker_id=task.worker_id,
        reviewer_id=task.reviewer_id,
        qa_result=task.qa_result,
        output_path=task.output_path,
        error_message=task.error_message,
        version=task.version,
        created_at=task.created_at,
        updated_at=task.updated_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        depends_on=dep_ids,
    )


async def _get_board_data(
    project_id: str,
    db: AsyncSession,
    redis_client: aioredis.Redis,
) -> dict:
    """Build board data dict for a project."""
    import uuid as _uuid

    pid = _uuid.UUID(project_id)
    repo = TaskRepository(db)
    tasks = await repo.list_by_project(pid, limit=500)

    # Group tasks by status
    columns: dict[str, list] = {status.value: [] for status in models.TaskStatus}
    for task in tasks:
        task_resp = _build_task_response(task)
        columns[task.status.value].append(task_resp.model_dump(mode="json"))

    # Stats
    status_counts = await repo.count_by_status(pid)
    total = sum(status_counts.values())
    stats: dict[str, int] = {"total": total}
    for status in models.TaskStatus:
        stats[status.value] = status_counts.get(status.value, 0)

    # Worker stats
    registry = WorkerRegistry(redis_client)
    try:
        workers = await registry.get_all_workers()
    except Exception:
        workers = []
    idle = sum(1 for w in workers if w.get("status") == "idle")
    busy = sum(1 for w in workers if w.get("status") == "busy")

    return {
        "project_id": project_id,
        "columns": columns,
        "stats": stats,
        "workers": {"total": len(workers), "idle": idle, "busy": busy},
    }


@router.get("/{project_id}")
async def get_board(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get full board state for a project."""
    redis_client: aioredis.Redis = request.app.state.redis
    return await _get_board_data(project_id, db, redis_client)


async def _board_event_generator(
    project_id: str,
    redis_client: aioredis.Redis,
) -> AsyncGenerator[dict, None]:
    """Subscribe to events:board stream and yield matching events."""
    last_id = "$"
    while True:
        try:
            messages = await redis_client.xread(
                streams={"events:board": last_id},
                count=10,
                block=5000,
            )
            if messages:
                for _stream_name, entries in messages:
                    for msg_id, data in entries:
                        last_id = msg_id
                        event_project_id = data.get("project_id", "")
                        if event_project_id == project_id:
                            yield {"event": data.get("event", "update"), "data": json.dumps(data)}
        except asyncio.CancelledError:
            break


@router.get("/{project_id}/events")
async def board_events(
    project_id: str,
    request: Request,
) -> EventSourceResponse:
    """SSE stream for board events."""
    redis_client: aioredis.Redis = request.app.state.redis
    return EventSourceResponse(_board_event_generator(project_id, redis_client))


@router.websocket("/ws/{project_id}")
async def board_websocket(
    websocket: WebSocket,
    project_id: str,
) -> None:
    """WebSocket endpoint for real-time board updates."""
    await websocket.accept()
    redis_client: aioredis.Redis = websocket.app.state.redis

    try:
        # Send initial board state (we don't have db session in WS easily, send a welcome)
        await websocket.send_json({"event": "connected", "project_id": project_id})

        # Poll events:board and forward
        last_id = "$"
        while True:
            messages = await redis_client.xread(
                streams={"events:board": last_id},
                count=10,
                block=5000,
            )
            if messages:
                for _stream_name, entries in messages:
                    for msg_id, data in entries:
                        last_id = msg_id
                        event_project_id = data.get("project_id", "")
                        if event_project_id == project_id:
                            await websocket.send_json(data)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
