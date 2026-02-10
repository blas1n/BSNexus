from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from backend.src.main import app
from backend.src.models import Phase, PhaseStatus, Project, ProjectStatus, Task, TaskPriority, TaskStatus


async def create_project_phase_task(db_session, status: TaskStatus = TaskStatus.ready) -> tuple[Project, Phase, Task]:
    """Helper to create a project with a phase and task."""
    now = datetime.now(timezone.utc)
    project = Project(
        id=uuid.uuid4(),
        name="Test Project",
        description="Test",
        repo_path="/test",
        status=ProjectStatus.active,
        created_at=now,
        updated_at=now,
    )
    db_session.add(project)
    await db_session.flush()

    phase = Phase(
        id=uuid.uuid4(),
        project_id=project.id,
        name="Phase 1",
        branch_name="phase-1",
        order=1,
        status=PhaseStatus.active,
        created_at=now,
        updated_at=now,
    )
    db_session.add(phase)
    await db_session.flush()

    task = Task(
        id=uuid.uuid4(),
        project_id=project.id,
        phase_id=phase.id,
        title="Test Task",
        status=status,
        priority=TaskPriority.medium,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db_session.add(task)
    await db_session.commit()

    return project, phase, task


@pytest.fixture(autouse=True)
def mock_redis():
    """Set app.state.redis to an AsyncMock for all board tests."""
    mock = AsyncMock()
    mock.scan_iter = AsyncMock(return_value=[]).__aiter__
    # Make scan_iter return an empty async iterator by default
    mock.scan_iter.return_value = _empty_async_iter()
    app.state.redis = mock
    yield mock


async def _empty_async_iter():
    """Empty async iterator helper."""
    return
    yield  # noqa: RET504 — makes this an async generator


@pytest.mark.asyncio
async def test_get_board_empty_project(client, db_session, mock_redis):
    """GET /api/board/{project_id} with no tasks returns all columns empty and stats all zeros."""
    now = datetime.now(timezone.utc)
    project = Project(
        id=uuid.uuid4(),
        name="Empty Project",
        description="No tasks",
        repo_path="/empty",
        status=ProjectStatus.active,
        created_at=now,
        updated_at=now,
    )
    db_session.add(project)
    await db_session.commit()

    response = await client.get(f"/api/board/{project.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["project_id"] == str(project.id)

    # All columns should be empty
    for status in TaskStatus:
        assert status.value in data["columns"]
        assert data["columns"][status.value] == []

    # Stats should all be zero
    assert data["stats"]["total"] == 0
    for status in TaskStatus:
        assert data["stats"][status.value] == 0

    # Workers section should be present
    assert "workers" in data


@pytest.mark.asyncio
async def test_get_board_with_tasks(client, db_session, mock_redis):
    """GET /api/board/{project_id} groups tasks by status into correct columns."""
    now = datetime.now(timezone.utc)
    project = Project(
        id=uuid.uuid4(),
        name="Board Project",
        description="With tasks",
        repo_path="/board",
        status=ProjectStatus.active,
        created_at=now,
        updated_at=now,
    )
    db_session.add(project)
    await db_session.flush()

    phase = Phase(
        id=uuid.uuid4(),
        project_id=project.id,
        name="Phase 1",
        branch_name="phase-1",
        order=1,
        status=PhaseStatus.active,
        created_at=now,
        updated_at=now,
    )
    db_session.add(phase)
    await db_session.flush()

    # Create tasks in different statuses
    statuses_to_create = [TaskStatus.ready, TaskStatus.ready, TaskStatus.in_progress, TaskStatus.done]
    for i, status in enumerate(statuses_to_create):
        task = Task(
            id=uuid.uuid4(),
            project_id=project.id,
            phase_id=phase.id,
            title=f"Task {i}",
            status=status,
            priority=TaskPriority.medium,
            version=1,
            created_at=now,
            updated_at=now,
        )
        db_session.add(task)

    await db_session.commit()

    response = await client.get(f"/api/board/{project.id}")

    assert response.status_code == 200
    data = response.json()

    # Check task grouping
    assert len(data["columns"]["ready"]) == 2
    assert len(data["columns"]["in_progress"]) == 1
    assert len(data["columns"]["done"]) == 1
    assert len(data["columns"]["waiting"]) == 0
    assert len(data["columns"]["queued"]) == 0
    assert len(data["columns"]["review"]) == 0
    assert len(data["columns"]["rejected"]) == 0


@pytest.mark.asyncio
async def test_get_board_stats(client, db_session, mock_redis):
    """GET /api/board/{project_id} returns accurate stat counts."""
    now = datetime.now(timezone.utc)
    project = Project(
        id=uuid.uuid4(),
        name="Stats Project",
        description="For stats",
        repo_path="/stats",
        status=ProjectStatus.active,
        created_at=now,
        updated_at=now,
    )
    db_session.add(project)
    await db_session.flush()

    phase = Phase(
        id=uuid.uuid4(),
        project_id=project.id,
        name="Phase 1",
        branch_name="phase-1",
        order=1,
        status=PhaseStatus.active,
        created_at=now,
        updated_at=now,
    )
    db_session.add(phase)
    await db_session.flush()

    # Create 3 ready tasks and 2 done tasks
    for i in range(3):
        db_session.add(
            Task(
                id=uuid.uuid4(),
                project_id=project.id,
                phase_id=phase.id,
                title=f"Ready Task {i}",
                status=TaskStatus.ready,
                priority=TaskPriority.medium,
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
    for i in range(2):
        db_session.add(
            Task(
                id=uuid.uuid4(),
                project_id=project.id,
                phase_id=phase.id,
                title=f"Done Task {i}",
                status=TaskStatus.done,
                priority=TaskPriority.medium,
                version=1,
                created_at=now,
                updated_at=now,
            )
        )

    await db_session.commit()

    response = await client.get(f"/api/board/{project.id}")

    assert response.status_code == 200
    data = response.json()

    assert data["stats"]["total"] == 5
    assert data["stats"]["ready"] == 3
    assert data["stats"]["done"] == 2
    assert data["stats"]["waiting"] == 0
    assert data["stats"]["in_progress"] == 0


@pytest.mark.asyncio
async def test_get_board_workers(client, db_session, mock_redis):
    """GET /api/board/{project_id} returns workers section with total, idle, busy counts."""
    project, _phase, _task = await create_project_phase_task(db_session)

    response = await client.get(f"/api/board/{project.id}")

    assert response.status_code == 200
    data = response.json()

    # Workers section should be present with expected keys
    assert "workers" in data
    assert "total" in data["workers"]
    assert "idle" in data["workers"]
    assert "busy" in data["workers"]

    # With mock redis returning no workers, all should be 0
    assert data["workers"]["total"] == 0
    assert data["workers"]["idle"] == 0
    assert data["workers"]["busy"] == 0
