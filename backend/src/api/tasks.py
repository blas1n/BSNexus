from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.src import models, schemas
from backend.src.core.state_machine import TaskStateMachine
from backend.src.models import Task, task_dependencies
from backend.src.storage.database import get_db

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

state_machine = TaskStateMachine()


# ── Helpers ───────────────────────────────────────────────────────────


async def detect_circular_dependency(
    task_id: UUID,
    depends_on: list[UUID],
    db: AsyncSession,
) -> bool:
    """Detect circular dependencies using DFS."""
    visited: set[UUID] = set()

    async def dfs(current_id: UUID) -> bool:
        if current_id == task_id:
            return True
        if current_id in visited:
            return False
        visited.add(current_id)

        result = await db.execute(
            select(task_dependencies.c.dependency_id).where(task_dependencies.c.task_id == current_id)
        )
        dep_ids = result.scalars().all()
        for dep_id in dep_ids:
            if await dfs(dep_id):
                return True
        return False

    for dep_id in depends_on:
        if dep_id == task_id:
            return True
        if await dfs(dep_id):
            return True
    return False


def build_task_response(task: Task) -> schemas.TaskResponse:
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


# ── Endpoints ─────────────────────────────────────────────────────────


@router.post("/", response_model=schemas.TaskResponse, status_code=201)
async def create_task(
    task_data: schemas.TaskCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> schemas.TaskResponse:
    """Create a new task."""
    # Validate depends_on tasks exist
    if task_data.depends_on:
        result = await db.execute(select(Task.id).where(Task.id.in_(task_data.depends_on)))
        existing_ids = set(result.scalars().all())
        missing = set(task_data.depends_on) - existing_ids
        if missing:
            raise HTTPException(status_code=400, detail=f"Dependency tasks not found: {missing}")

        # Detect circular dependencies
        # Use a temporary UUID since the task doesn't exist yet
        import uuid as uuid_mod

        temp_id = uuid_mod.uuid4()
        if await detect_circular_dependency(temp_id, task_data.depends_on, db):
            raise HTTPException(status_code=400, detail="Circular dependency detected")

    # Create Task ORM object
    task = Task(
        project_id=task_data.project_id,
        phase_id=task_data.phase_id,
        title=task_data.title,
        description=task_data.description,
        priority=models.TaskPriority(task_data.priority.value),
        worker_prompt={"prompt": task_data.worker_prompt},
        qa_prompt={"prompt": task_data.qa_prompt},
        version=1,
    )

    # Set status based on dependencies
    if task_data.depends_on:
        task.status = models.TaskStatus.waiting
    else:
        task.status = models.TaskStatus.ready

    db.add(task)
    await db.flush()

    # Add dependency relationships
    if task_data.depends_on:
        for dep_id in task_data.depends_on:
            await db.execute(task_dependencies.insert().values(task_id=task.id, dependency_id=dep_id))

    # Load depends_on relationship for response
    await db.refresh(task, attribute_names=["depends_on"])
    await db.commit()
    await db.refresh(task)

    # Eagerly load depends_on after commit
    result = await db.execute(select(Task).where(Task.id == task.id).options(selectinload(Task.depends_on)))
    task = result.scalar_one()

    return build_task_response(task)


@router.get("/{task_id}", response_model=schemas.TaskResponse)
async def get_task(
    task_id: UUID,
    include_history: bool = Query(False),
    db: AsyncSession = Depends(get_db),
) -> schemas.TaskResponse:
    """Get a task by ID."""
    load_options = [selectinload(Task.depends_on)]
    if include_history:
        load_options.append(selectinload(Task.history))

    result = await db.execute(select(Task).where(Task.id == task_id).options(*load_options))
    task = result.scalar_one_or_none()

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return build_task_response(task)


@router.patch("/{task_id}", response_model=schemas.TaskResponse)
async def update_task(
    task_id: UUID,
    task_data: schemas.TaskUpdate,
    db: AsyncSession = Depends(get_db),
) -> schemas.TaskResponse:
    """Update a task (only in waiting or ready status)."""
    result = await db.execute(select(Task).where(Task.id == task_id).options(selectinload(Task.depends_on)))
    task = result.scalar_one_or_none()

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status not in (models.TaskStatus.waiting, models.TaskStatus.ready):
        raise HTTPException(status_code=400, detail="Task can only be updated in waiting or ready status")

    update_data = task_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "priority" and value is not None:
            setattr(task, field, models.TaskPriority(value))
        else:
            setattr(task, field, value)

    await db.commit()
    await db.refresh(task)

    # Reload with depends_on
    result = await db.execute(select(Task).where(Task.id == task_id).options(selectinload(Task.depends_on)))
    task = result.scalar_one()

    return build_task_response(task)


@router.post("/{task_id}/transition", response_model=schemas.TransitionResponse)
async def transition_task(
    task_id: UUID,
    transition: schemas.TaskTransition,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> schemas.TransitionResponse:
    """Transition a task to a new status."""
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # Convert schema TaskStatus to model TaskStatus
    model_status = models.TaskStatus(transition.new_status.value)

    # Get stream_manager from app state
    stream_manager = request.app.state.stream_manager

    # Store previous status for response
    previous_status = task.status

    try:
        await state_machine.transition(
            task,
            model_status,
            reason=transition.reason,
            actor=transition.actor,
            db_session=db,
            stream_manager=stream_manager,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    await db.commit()

    return schemas.TransitionResponse(
        task_id=task.id,
        status=schemas.TaskStatus(task.status.value),
        previous_status=schemas.TaskStatus(previous_status.value),
        transition={
            "from": previous_status.value,
            "to": task.status.value,
            "reason": transition.reason,
            "actor": transition.actor,
        },
    )


@router.get("/by-project/{project_id}", response_model=list[schemas.TaskResponse])
async def list_project_tasks(
    project_id: UUID,
    status: Optional[str] = Query(None),
    phase_id: Optional[UUID] = Query(None),
    priority: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[schemas.TaskResponse]:
    """List tasks for a project with optional filters."""
    query = select(Task).where(Task.project_id == project_id)

    if status is not None:
        query = query.where(Task.status == models.TaskStatus(status))

    if phase_id is not None:
        query = query.where(Task.phase_id == phase_id)

    if priority is not None:
        query = query.where(Task.priority == models.TaskPriority(priority))

    query = query.order_by(Task.created_at.desc()).limit(limit).offset(offset)
    query = query.options(selectinload(Task.depends_on))

    result = await db.execute(query)
    tasks = result.scalars().all()

    return [build_task_response(task) for task in tasks]
