from __future__ import annotations

import asyncio
import uuid

from backend.src import models
from backend.src.core.orchestrator import PMOrchestrator
from backend.src.core.state_machine import TaskStateMachine
from backend.src.repositories.task_repository import TaskRepository
from backend.src.storage.database import async_session, get_db
from backend.src.utils.worker_registry import WorkerRegistry
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/pm", tags=["pm"])


# -- Dependency helpers --------------------------------------------------------


def _get_registry(request: Request) -> WorkerRegistry:
    """Build a WorkerRegistry from the app-level Redis client."""
    return WorkerRegistry(request.app.state.redis)


def _get_stream_manager(request: Request) -> object:
    """Get the RedisStreamManager from app state."""
    return request.app.state.stream_manager


def _ensure_orchestrators(request: Request) -> dict[str, dict]:
    """Ensure the orchestrators dict exists on app.state and return it."""
    if not hasattr(request.app.state, "orchestrators"):
        request.app.state.orchestrators = {}
    return request.app.state.orchestrators


# -- Endpoints ----------------------------------------------------------------


@router.post("/{project_id}/start")
async def start_orchestration(
    project_id: uuid.UUID,
    request: Request,
) -> dict:
    """Start orchestration for a project."""
    orchestrators = _ensure_orchestrators(request)
    pid = str(project_id)

    if pid in orchestrators and orchestrators[pid].get("running"):
        raise HTTPException(
            status_code=409, detail="Orchestrator already running for this project"
        )

    stream_manager = _get_stream_manager(request)
    registry = _get_registry(request)
    state_machine = TaskStateMachine()

    orchestrator = PMOrchestrator(
        stream_manager=stream_manager,
        worker_registry=registry,
        state_machine=state_machine,
    )

    task = asyncio.create_task(orchestrator.start(project_id, async_session))

    orchestrators[pid] = {
        "orchestrator": orchestrator,
        "task": task,
        "running": True,
    }

    return {"detail": "Orchestration started", "project_id": pid}


@router.post("/{project_id}/pause")
async def pause_orchestration(
    project_id: uuid.UUID,
    request: Request,
) -> dict:
    """Pause orchestration for a project."""
    orchestrators = _ensure_orchestrators(request)
    pid = str(project_id)

    entry = orchestrators.get(pid)
    if not entry or not entry.get("running"):
        raise HTTPException(
            status_code=404, detail="No running orchestrator for this project"
        )

    orchestrator: PMOrchestrator = entry["orchestrator"]
    await orchestrator.stop()
    entry["running"] = False

    return {"detail": "Orchestration paused", "project_id": pid}


@router.get("/{project_id}/status")
async def get_orchestration_status(
    project_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get orchestration status for a project."""
    orchestrators = _ensure_orchestrators(request)
    pid = str(project_id)

    entry = orchestrators.get(pid)
    running = bool(entry and entry.get("running"))

    # Worker counts
    registry = _get_registry(request)
    workers = await registry.get_all_workers()
    idle_count = sum(1 for w in workers if w["status"] == "idle")
    busy_count = sum(1 for w in workers if w["status"] == "busy")

    # Task counts by status
    repo = TaskRepository(db)
    task_counts = await repo.count_by_status(project_id)

    return {
        "project_id": pid,
        "running": running,
        "workers": {
            "idle": idle_count,
            "busy": busy_count,
            "total": len(workers),
        },
        "tasks": task_counts,
    }


@router.post("/{project_id}/promote-waiting")
async def promote_waiting_tasks(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Promote WAITING tasks with all dependencies met (or none) to READY."""
    repo = TaskRepository(db)
    state_machine = TaskStateMachine()
    waiting_tasks = await repo.list_by_project(project_id, status=models.TaskStatus.waiting, limit=500)

    promoted: list[dict] = []
    for task in waiting_tasks:
        if await repo.check_dependencies_met(task.id):
            await state_machine.transition(
                task=task,
                new_status=models.TaskStatus.ready,
                reason="All dependencies met",
                actor="system",
                db_session=db,
            )
            promoted.append({"task_id": str(task.id), "title": task.title})

    await db.commit()
    return {"detail": f"Promoted {len(promoted)} tasks to ready", "promoted": promoted}


@router.post("/{project_id}/queue-next")
async def queue_next_task(
    project_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Manually queue the highest-priority READY task."""
    stream_manager = _get_stream_manager(request)
    registry = _get_registry(request)
    state_machine = TaskStateMachine()

    orchestrator = PMOrchestrator(
        stream_manager=stream_manager,
        worker_registry=registry,
        state_machine=state_machine,
    )

    task = await orchestrator.queue_next(project_id, db)
    if not task:
        raise HTTPException(status_code=404, detail="No ready tasks to queue")

    await db.commit()

    return {
        "detail": "Task queued",
        "task_id": str(task.id),
        "title": task.title,
        "priority": task.priority.value,
    }
