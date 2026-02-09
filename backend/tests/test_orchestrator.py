from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.src.core.orchestrator import PMOrchestrator
from backend.src.models import Task, TaskPriority, TaskStatus
from backend.src.repositories.task_repository import PRIORITY_ORDER


# -- Helpers -------------------------------------------------------------------


def make_task(status: TaskStatus = TaskStatus.waiting, **kwargs) -> Task:
    """Create a Task object without touching the DB."""
    now = datetime.now(timezone.utc)
    return Task(
        id=kwargs.get("id", uuid.uuid4()),
        project_id=kwargs.get("project_id", uuid.uuid4()),
        phase_id=kwargs.get("phase_id", uuid.uuid4()),
        title=kwargs.get("title", "Test Task"),
        description=kwargs.get("description", None),
        status=status,
        priority=kwargs.get("priority", TaskPriority.medium),
        version=kwargs.get("version", 1),
        worker_id=kwargs.get("worker_id", None),
        reviewer_id=kwargs.get("reviewer_id", None),
        worker_prompt=None,
        qa_prompt=None,
        branch_name=None,
        commit_hash=None,
        qa_result=None,
        output_path=None,
        error_message=None,
        started_at=None,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )


# -- Fixtures ------------------------------------------------------------------


@pytest.fixture
def mock_stream() -> AsyncMock:
    manager = AsyncMock()
    manager.publish = AsyncMock(return_value="mock-id")
    manager.publish_board_event = AsyncMock()
    manager.consume = AsyncMock(return_value=[])
    manager.acknowledge = AsyncMock()
    return manager


@pytest.fixture
def mock_registry() -> AsyncMock:
    registry = AsyncMock()
    registry.get_all_workers = AsyncMock(return_value=[])
    registry.set_busy = AsyncMock()
    registry.set_idle = AsyncMock()
    return registry


@pytest.fixture
def mock_state_machine() -> AsyncMock:
    sm = AsyncMock()
    sm.transition = AsyncMock()
    return sm


@pytest.fixture
def orchestrator(mock_stream: AsyncMock, mock_registry: AsyncMock, mock_state_machine: AsyncMock) -> PMOrchestrator:
    return PMOrchestrator(
        stream_manager=mock_stream,
        worker_registry=mock_registry,
        state_machine=mock_state_machine,
    )


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    return db


# -- list_ready_by_priority (via TaskRepository) ------------------------------


async def test_list_ready_by_priority_sorted(orchestrator: PMOrchestrator) -> None:
    """TaskRepository.list_ready_by_priority should return tasks sorted by priority (critical first)."""
    project_id = uuid.uuid4()
    low_task = make_task(status=TaskStatus.ready, priority=TaskPriority.low, project_id=project_id)
    critical_task = make_task(status=TaskStatus.ready, priority=TaskPriority.critical, project_id=project_id)
    high_task = make_task(status=TaskStatus.ready, priority=TaskPriority.high, project_id=project_id)
    medium_task = make_task(status=TaskStatus.ready, priority=TaskPriority.medium, project_id=project_id)

    mock_db = AsyncMock()
    sorted_tasks = [critical_task, high_task, medium_task, low_task]

    with patch(
        "backend.src.core.orchestrator.TaskRepository"
    ) as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.list_ready_by_priority = AsyncMock(return_value=sorted_tasks)
        MockRepo.return_value = mock_repo_instance

        result = await orchestrator.queue_next(project_id, mock_db)

    assert result is not None
    assert result.priority == TaskPriority.critical


async def test_list_ready_by_priority_empty() -> None:
    """TaskRepository.list_ready_by_priority should return empty list when no ready tasks."""
    from backend.src.repositories.task_repository import TaskRepository

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute = AsyncMock(return_value=mock_result)

    repo = TaskRepository(mock_db)
    tasks = await repo.list_ready_by_priority(uuid.uuid4())

    assert tasks == []


# -- _process_result: execution ------------------------------------------------


async def test_process_result_execution_success_assigns_reviewer(
    orchestrator: PMOrchestrator, mock_db: AsyncMock, mock_registry: AsyncMock, mock_state_machine: AsyncMock
) -> None:
    """Execution success should assign a reviewer via _assign_reviewer."""
    task = make_task(status=TaskStatus.in_progress)

    reviewer_worker = {"id": "reviewer-1", "status": "idle"}
    mock_registry.get_all_workers.return_value = [
        {"id": "executor-1", "status": "busy"},
        reviewer_worker,
    ]

    result = {
        "task_id": str(task.id),
        "type": "execution",
        "success": "true",
        "worker_id": "executor-1",
        "_message_id": "msg-1",
    }

    with patch("backend.src.core.orchestrator.TaskRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=task)
        MockRepo.return_value = mock_repo_instance

        await orchestrator._process_result(result, mock_db)

    # Should transition to review with reviewer_id
    mock_state_machine.transition.assert_called_once()
    call_kwargs = mock_state_machine.transition.call_args[1]
    assert call_kwargs["new_status"] == TaskStatus.review
    assert call_kwargs["reviewer_id"] == "reviewer-1"
    # Should set reviewer to busy
    mock_registry.set_busy.assert_called_once_with("reviewer-1", str(task.id))


async def test_process_result_execution_failure_rejects_and_idles(
    orchestrator: PMOrchestrator, mock_db: AsyncMock, mock_registry: AsyncMock, mock_state_machine: AsyncMock
) -> None:
    """Execution failure should reject the task and set worker to idle."""
    task = make_task(status=TaskStatus.in_progress)

    result = {
        "task_id": str(task.id),
        "type": "execution",
        "success": "false",
        "worker_id": "worker-1",
        "error_message": "Build failed",
        "_message_id": "msg-1",
    }

    with patch("backend.src.core.orchestrator.TaskRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=task)
        MockRepo.return_value = mock_repo_instance

        await orchestrator._process_result(result, mock_db)

    mock_state_machine.transition.assert_called_once()
    call_kwargs = mock_state_machine.transition.call_args[1]
    assert call_kwargs["new_status"] == TaskStatus.rejected
    assert "Execution failed: Build failed" in call_kwargs["reason"]
    mock_registry.set_idle.assert_called_once_with("worker-1")


async def test_process_result_task_not_found(
    orchestrator: PMOrchestrator, mock_db: AsyncMock, mock_state_machine: AsyncMock
) -> None:
    """When the task is not found, _process_result should return early without transitions."""
    result = {
        "task_id": str(uuid.uuid4()),
        "type": "execution",
        "success": "true",
        "worker_id": "w-1",
        "_message_id": "msg-1",
    }

    with patch("backend.src.core.orchestrator.TaskRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=None)
        MockRepo.return_value = mock_repo_instance

        await orchestrator._process_result(result, mock_db)

    mock_state_machine.transition.assert_not_called()


# -- _process_result: QA -------------------------------------------------------


async def test_process_result_qa_pass_transitions_to_done(
    orchestrator: PMOrchestrator, mock_db: AsyncMock, mock_registry: AsyncMock, mock_state_machine: AsyncMock
) -> None:
    """QA pass should transition task to done and set reviewer idle."""
    task = make_task(status=TaskStatus.review)

    result = {
        "task_id": str(task.id),
        "type": "qa",
        "success": "true",
        "passed": "true",
        "worker_id": "reviewer-1",
        "_message_id": "msg-1",
    }

    with patch("backend.src.core.orchestrator.TaskRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=task)
        MockRepo.return_value = mock_repo_instance

        await orchestrator._process_result(result, mock_db)

    mock_state_machine.transition.assert_called_once()
    call_kwargs = mock_state_machine.transition.call_args[1]
    assert call_kwargs["new_status"] == TaskStatus.done
    assert call_kwargs["reason"] == "QA passed"
    mock_registry.set_idle.assert_called_once_with("reviewer-1")


async def test_process_result_qa_fail_rejects(
    orchestrator: PMOrchestrator, mock_db: AsyncMock, mock_registry: AsyncMock, mock_state_machine: AsyncMock
) -> None:
    """QA failure should reject the task and set reviewer idle."""
    task = make_task(status=TaskStatus.review)

    result = {
        "task_id": str(task.id),
        "type": "qa",
        "success": "false",
        "passed": "false",
        "feedback": "Tests not passing",
        "worker_id": "reviewer-1",
        "_message_id": "msg-1",
    }

    with patch("backend.src.core.orchestrator.TaskRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=task)
        MockRepo.return_value = mock_repo_instance

        await orchestrator._process_result(result, mock_db)

    mock_state_machine.transition.assert_called_once()
    call_kwargs = mock_state_machine.transition.call_args[1]
    assert call_kwargs["new_status"] == TaskStatus.rejected
    assert "QA failed: Tests not passing" in call_kwargs["reason"]
    mock_registry.set_idle.assert_called_once_with("reviewer-1")


# -- _assign_reviewer ----------------------------------------------------------


async def test_assign_reviewer_picks_different_worker(
    orchestrator: PMOrchestrator, mock_db: AsyncMock, mock_registry: AsyncMock, mock_state_machine: AsyncMock
) -> None:
    """_assign_reviewer should pick a reviewer different from the executor."""
    task = make_task(status=TaskStatus.in_progress)

    mock_registry.get_all_workers.return_value = [
        {"id": "executor-1", "status": "idle"},
        {"id": "reviewer-1", "status": "idle"},
        {"id": "reviewer-2", "status": "idle"},
    ]

    await orchestrator._assign_reviewer(task, mock_db, "executor-1")

    mock_state_machine.transition.assert_called_once()
    call_kwargs = mock_state_machine.transition.call_args[1]
    assert call_kwargs["new_status"] == TaskStatus.review
    assert call_kwargs["reviewer_id"] == "reviewer-1"
    mock_registry.set_busy.assert_called_once_with("reviewer-1", str(task.id))


async def test_assign_reviewer_no_available_reviewers(
    orchestrator: PMOrchestrator, mock_db: AsyncMock, mock_registry: AsyncMock, mock_state_machine: AsyncMock
) -> None:
    """_assign_reviewer should do nothing when no reviewers are available."""
    task = make_task(status=TaskStatus.in_progress)

    # Only the executor is available, no other idle workers
    mock_registry.get_all_workers.return_value = [
        {"id": "executor-1", "status": "idle"},
    ]

    await orchestrator._assign_reviewer(task, mock_db, "executor-1")

    mock_state_machine.transition.assert_not_called()
    mock_registry.set_busy.assert_not_called()


async def test_assign_reviewer_all_others_busy(
    orchestrator: PMOrchestrator, mock_db: AsyncMock, mock_registry: AsyncMock, mock_state_machine: AsyncMock
) -> None:
    """_assign_reviewer should do nothing when all other workers are busy."""
    task = make_task(status=TaskStatus.in_progress)

    mock_registry.get_all_workers.return_value = [
        {"id": "executor-1", "status": "idle"},
        {"id": "reviewer-1", "status": "busy"},
    ]

    await orchestrator._assign_reviewer(task, mock_db, "executor-1")

    mock_state_machine.transition.assert_not_called()
    mock_registry.set_busy.assert_not_called()


# -- queue_next ----------------------------------------------------------------


async def test_queue_next_queues_highest_priority(
    orchestrator: PMOrchestrator, mock_state_machine: AsyncMock
) -> None:
    """queue_next should queue the highest priority ready task."""
    project_id = uuid.uuid4()
    critical_task = make_task(status=TaskStatus.ready, priority=TaskPriority.critical, project_id=project_id)
    low_task = make_task(status=TaskStatus.ready, priority=TaskPriority.low, project_id=project_id)

    mock_db = AsyncMock()

    with patch("backend.src.core.orchestrator.TaskRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.list_ready_by_priority = AsyncMock(return_value=[critical_task, low_task])
        MockRepo.return_value = mock_repo_instance

        result = await orchestrator.queue_next(project_id, mock_db)

    assert result is not None
    assert result.priority == TaskPriority.critical
    mock_state_machine.transition.assert_called_once()
    call_kwargs = mock_state_machine.transition.call_args[1]
    assert call_kwargs["new_status"] == TaskStatus.queued
    assert call_kwargs["actor"] == "user"


async def test_queue_next_returns_none_when_no_ready_tasks(
    orchestrator: PMOrchestrator,
) -> None:
    """queue_next should return None when there are no ready tasks."""
    project_id = uuid.uuid4()
    mock_db = AsyncMock()

    with patch("backend.src.core.orchestrator.TaskRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.list_ready_by_priority = AsyncMock(return_value=[])
        MockRepo.return_value = mock_repo_instance

        result = await orchestrator.queue_next(project_id, mock_db)

    assert result is None


# -- stop ----------------------------------------------------------------------


async def test_stop_sets_running_to_false(orchestrator: PMOrchestrator) -> None:
    """stop() should set _running to False."""
    orchestrator._running = True
    await orchestrator.stop()
    assert orchestrator._running is False


# -- PRIORITY_ORDER ------------------------------------------------------------


def test_priority_order_values() -> None:
    """Verify PRIORITY_ORDER has correct ordering values."""
    assert PRIORITY_ORDER[TaskPriority.critical] == 0
    assert PRIORITY_ORDER[TaskPriority.high] == 1
    assert PRIORITY_ORDER[TaskPriority.medium] == 2
    assert PRIORITY_ORDER[TaskPriority.low] == 3
