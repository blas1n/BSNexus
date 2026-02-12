from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src import models, schemas
from backend.src.storage.database import get_db

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=schemas.DashboardStatsResponse)
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)) -> schemas.DashboardStatsResponse:
    """Return aggregated dashboard statistics for projects, tasks, and workers."""
    # Project stats
    project_result = await db.execute(select(models.Project))
    projects = project_result.scalars().all()
    total_projects = len(projects)
    active_projects = sum(1 for p in projects if p.status == models.ProjectStatus.active)
    completed_projects = sum(1 for p in projects if p.status == models.ProjectStatus.completed)

    # Task stats
    task_result = await db.execute(select(models.Task))
    tasks = task_result.scalars().all()
    total_tasks = len(tasks)
    active_tasks = sum(
        1
        for t in tasks
        if t.status in (models.TaskStatus.ready, models.TaskStatus.queued, models.TaskStatus.in_progress, models.TaskStatus.review)
    )
    in_progress_tasks = sum(1 for t in tasks if t.status == models.TaskStatus.in_progress)
    done_tasks = sum(1 for t in tasks if t.status == models.TaskStatus.done)
    completion_rate = round((done_tasks / total_tasks * 100), 1) if total_tasks > 0 else 0.0

    # Worker stats
    worker_result = await db.execute(select(models.Worker))
    workers = worker_result.scalars().all()
    total_workers = len(workers)
    online_workers = sum(
        1 for w in workers if w.status in (models.WorkerStatus.idle, models.WorkerStatus.busy)
    )
    busy_workers = sum(1 for w in workers if w.status == models.WorkerStatus.busy)

    return schemas.DashboardStatsResponse(
        total_projects=total_projects,
        active_projects=active_projects,
        completed_projects=completed_projects,
        total_tasks=total_tasks,
        active_tasks=active_tasks,
        in_progress_tasks=in_progress_tasks,
        done_tasks=done_tasks,
        completion_rate=completion_rate,
        total_workers=total_workers,
        online_workers=online_workers,
        busy_workers=busy_workers,
    )
