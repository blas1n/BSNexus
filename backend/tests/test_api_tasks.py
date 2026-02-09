from __future__ import annotations

import uuid
from datetime import datetime, timezone

from httpx import AsyncClient

from backend.src.models import Phase, PhaseStatus, Project, ProjectStatus, Task, TaskPriority, TaskStatus


async def create_project_and_phase(db_session) -> tuple[Project, Phase]:
    """Helper to create a project and phase for task tests."""
    now = datetime.now(timezone.utc)
    project = Project(
        id=uuid.uuid4(),
        name="Test Project",
        description="Test Description",
        repo_path="/test/repo",
        status=ProjectStatus.active,
        created_at=now,
        updated_at=now,
    )
    db_session.add(project)

    phase = Phase(
        id=uuid.uuid4(),
        project_id=project.id,
        name="Test Phase",
        branch_name="phase/test",
        order=1,
        status=PhaseStatus.active,
        created_at=now,
        updated_at=now,
    )
    db_session.add(phase)
    await db_session.commit()
    return project, phase


async def test_create_task_success(client: AsyncClient, db_session):
    """POST /api/tasks/ returns 201 with valid data."""
    project, phase = await create_project_and_phase(db_session)

    response = await client.post(
        "/api/tasks/",
        json={
            "project_id": str(project.id),
            "phase_id": str(phase.id),
            "title": "Test Task",
            "description": "Test description",
            "priority": "medium",
            "depends_on": [],
            "worker_prompt": "do something",
            "qa_prompt": "check something",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Task"
    assert data["status"] == "ready"  # No dependencies means READY
    assert data["priority"] == "medium"
    assert data["project_id"] == str(project.id)
    assert data["phase_id"] == str(phase.id)


async def test_create_task_dependency_not_found_400(client: AsyncClient, db_session):
    """POST /api/tasks/ with non-existent dependency returns 400."""
    project, phase = await create_project_and_phase(db_session)
    fake_dep_id = str(uuid.uuid4())

    response = await client.post(
        "/api/tasks/",
        json={
            "project_id": str(project.id),
            "phase_id": str(phase.id),
            "title": "Task with bad dep",
            "description": "Test",
            "priority": "medium",
            "depends_on": [fake_dep_id],
            "worker_prompt": "do something",
            "qa_prompt": "check something",
        },
    )

    assert response.status_code == 400
    assert "Dependency tasks not found" in response.json()["detail"]


async def test_get_task_success(client: AsyncClient, db_session):
    """GET /api/tasks/{id} returns 200."""
    project, phase = await create_project_and_phase(db_session)

    # Create a task via API
    create_response = await client.post(
        "/api/tasks/",
        json={
            "project_id": str(project.id),
            "phase_id": str(phase.id),
            "title": "Get Me Task",
            "description": "For retrieval",
            "priority": "high",
            "depends_on": [],
            "worker_prompt": "work",
            "qa_prompt": "check",
        },
    )
    task_id = create_response.json()["id"]

    response = await client.get(f"/api/tasks/{task_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == task_id
    assert data["title"] == "Get Me Task"


async def test_get_task_not_found_404(client: AsyncClient, db_session):
    """GET /api/tasks/{random_uuid} returns 404."""
    random_id = str(uuid.uuid4())
    response = await client.get(f"/api/tasks/{random_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


async def test_update_task_waiting_status(client: AsyncClient, db_session):
    """PATCH /api/tasks/{id} in waiting status returns 200."""
    project, phase = await create_project_and_phase(db_session)

    # Create a task with a dependency so it starts in WAITING status
    # First create the dependency task
    dep_response = await client.post(
        "/api/tasks/",
        json={
            "project_id": str(project.id),
            "phase_id": str(phase.id),
            "title": "Dep Task",
            "description": "dependency",
            "priority": "medium",
            "depends_on": [],
            "worker_prompt": "work",
            "qa_prompt": "check",
        },
    )
    dep_id = dep_response.json()["id"]

    # Create task that depends on the first one (will be WAITING)
    create_response = await client.post(
        "/api/tasks/",
        json={
            "project_id": str(project.id),
            "phase_id": str(phase.id),
            "title": "Waiting Task",
            "description": "will wait",
            "priority": "low",
            "depends_on": [dep_id],
            "worker_prompt": "work",
            "qa_prompt": "check",
        },
    )
    task_id = create_response.json()["id"]
    assert create_response.json()["status"] == "waiting"

    response = await client.patch(
        f"/api/tasks/{task_id}",
        json={"title": "Updated Title", "priority": "critical"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["priority"] == "critical"


async def test_update_task_in_progress_400(client: AsyncClient, db_session):
    """PATCH /api/tasks/{id} in IN_PROGRESS status returns 400."""
    project, phase = await create_project_and_phase(db_session)

    # Create task directly in IN_PROGRESS status in the DB
    now = datetime.now(timezone.utc)
    task = Task(
        id=uuid.uuid4(),
        project_id=project.id,
        phase_id=phase.id,
        title="In Progress Task",
        status=TaskStatus.in_progress,
        priority=TaskPriority.medium,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db_session.add(task)
    await db_session.commit()

    response = await client.patch(
        f"/api/tasks/{task.id}",
        json={"title": "Should Fail"},
    )

    assert response.status_code == 400
    assert "waiting or ready" in response.json()["detail"]


async def test_transition_task_valid(client: AsyncClient, db_session):
    """POST /api/tasks/{id}/transition with valid transition succeeds."""
    project, phase = await create_project_and_phase(db_session)

    # Create a task via API (no deps, so it starts as READY)
    create_response = await client.post(
        "/api/tasks/",
        json={
            "project_id": str(project.id),
            "phase_id": str(phase.id),
            "title": "Transition Task",
            "description": "for transition",
            "priority": "medium",
            "depends_on": [],
            "worker_prompt": "work",
            "qa_prompt": "check",
        },
    )
    task_id = create_response.json()["id"]
    assert create_response.json()["status"] == "ready"

    # Transition READY -> QUEUED
    response = await client.post(
        f"/api/tasks/{task_id}/transition",
        json={"new_status": "queued", "actor": "test"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "queued"
    assert data["previous_status"] == "ready"


async def test_transition_task_invalid_400(client: AsyncClient, db_session):
    """POST /api/tasks/{id}/transition with invalid transition returns 400."""
    project, phase = await create_project_and_phase(db_session)

    # Create a task (starts as READY)
    create_response = await client.post(
        "/api/tasks/",
        json={
            "project_id": str(project.id),
            "phase_id": str(phase.id),
            "title": "Invalid Transition Task",
            "description": "for invalid transition",
            "priority": "medium",
            "depends_on": [],
            "worker_prompt": "work",
            "qa_prompt": "check",
        },
    )
    task_id = create_response.json()["id"]

    # Try invalid transition READY -> DONE
    response = await client.post(
        f"/api/tasks/{task_id}/transition",
        json={"new_status": "done", "actor": "test"},
    )

    assert response.status_code == 400
    assert "Invalid transition" in response.json()["detail"]


async def test_list_project_tasks(client: AsyncClient, db_session):
    """GET /api/tasks/by-project/{project_id} returns list of tasks."""
    project, phase = await create_project_and_phase(db_session)

    # Create two tasks
    for title in ["Task One", "Task Two"]:
        await client.post(
            "/api/tasks/",
            json={
                "project_id": str(project.id),
                "phase_id": str(phase.id),
                "title": title,
                "description": f"Description for {title}",
                "priority": "medium",
                "depends_on": [],
                "worker_prompt": "work",
                "qa_prompt": "check",
            },
        )

    response = await client.get(f"/api/tasks/by-project/{project.id}")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    titles = {t["title"] for t in data}
    assert "Task One" in titles
    assert "Task Two" in titles
