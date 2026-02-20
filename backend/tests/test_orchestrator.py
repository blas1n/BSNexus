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
        worker_prompt=kwargs.get("worker_prompt", None),
        qa_prompt=kwargs.get("qa_prompt", None),
        branch_name=kwargs.get("branch_name", None),
        commit_hash=None,
        qa_result=None,
        output_path=None,
        error_message=kwargs.get("error_message", None),
        retry_count=kwargs.get("retry_count", 0),
        max_retries=kwargs.get("max_retries", 3),
        qa_feedback_history=kwargs.get("qa_feedback_history", None),
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
    # Redis client mock for ephemeral counters
    manager.redis = AsyncMock()
    manager.redis.get = AsyncMock(return_value=None)  # default: counter not set
    manager.redis.incr = AsyncMock(return_value=1)
    manager.redis.expire = AsyncMock()
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
        mock_repo_instance.count_active_tasks = AsyncMock(return_value=0)
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
    """Execution success should assign the executor worker as reviewer."""
    task = make_task(status=TaskStatus.in_progress)

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

    # Should transition to review with executor as reviewer
    mock_state_machine.transition.assert_called_once()
    call_kwargs = mock_state_machine.transition.call_args[1]
    assert call_kwargs["new_status"] == TaskStatus.review
    assert call_kwargs["reviewer_id"] == "executor-1"


async def test_process_result_execution_failure_retries_when_under_max(
    orchestrator: PMOrchestrator, mock_db: AsyncMock, mock_registry: AsyncMock, mock_state_machine: AsyncMock
) -> None:
    """Execution failure should auto-retry (transition to ready) when retry_count < max_retries."""
    task = make_task(status=TaskStatus.in_progress, retry_count=0, max_retries=3)

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
    assert call_kwargs["new_status"] == TaskStatus.ready
    assert "Execution failed" in call_kwargs["reason"]
    assert "attempt 1/3" in call_kwargs["reason"]
    mock_registry.set_idle.assert_called_once_with("worker-1")
    assert task.retry_count == 1


async def test_process_result_execution_failure_escalates_to_redesign(
    orchestrator: PMOrchestrator, mock_db: AsyncMock, mock_registry: AsyncMock, mock_state_machine: AsyncMock
) -> None:
    """Execution failure should escalate to redesign when retry_count >= max_retries."""
    task = make_task(status=TaskStatus.in_progress, retry_count=2, max_retries=3)

    result = {
        "task_id": str(task.id),
        "type": "execution",
        "success": "false",
        "worker_id": "worker-1",
        "error_message": "Build failed again",
        "_message_id": "msg-1",
    }

    with patch("backend.src.core.orchestrator.TaskRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=task)
        MockRepo.return_value = mock_repo_instance

        await orchestrator._process_result(result, mock_db)

    mock_state_machine.transition.assert_called_once()
    call_kwargs = mock_state_machine.transition.call_args[1]
    assert call_kwargs["new_status"] == TaskStatus.redesign
    assert "Max retries (3) exceeded" in call_kwargs["reason"]
    assert "Build failed again" in call_kwargs["reason"]
    mock_registry.set_idle.assert_called_once_with("worker-1")
    assert task.retry_count == 3


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


async def test_process_result_qa_failure_retries_when_under_max(
    orchestrator: PMOrchestrator,
    mock_db: AsyncMock,
    mock_registry: AsyncMock,
    mock_state_machine: AsyncMock,
    mock_stream: AsyncMock,
) -> None:
    """QA failure should auto-retry (transition to in_progress) when retry_count < max_retries."""
    project_id = uuid.uuid4()
    task = make_task(
        status=TaskStatus.review,
        retry_count=0,
        max_retries=3,
        project_id=project_id,
        title="Fix login",
    )

    result = {
        "task_id": str(task.id),
        "type": "qa",
        "success": "false",
        "passed": "false",
        "feedback": "Tests not passing",
        "worker_id": "reviewer-1",
        "_message_id": "msg-1",
    }

    with (
        patch("backend.src.core.orchestrator.TaskRepository") as MockRepo,
        patch("backend.src.core.orchestrator.ProjectRepository") as MockProjectRepo,
    ):
        mock_repo_instance = AsyncMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=task)
        MockRepo.return_value = mock_repo_instance

        mock_project = MagicMock()
        mock_project.repo_path = "/repos/test"
        mock_project_repo_instance = AsyncMock()
        mock_project_repo_instance.get_by_id = AsyncMock(return_value=mock_project)
        MockProjectRepo.return_value = mock_project_repo_instance

        await orchestrator._process_result(result, mock_db)

    # Should transition to in_progress for auto-retry
    mock_state_machine.transition.assert_called_once()
    call_kwargs = mock_state_machine.transition.call_args[1]
    assert call_kwargs["new_status"] == TaskStatus.in_progress
    assert "QA failed" in call_kwargs["reason"]
    assert "attempt 1/3" in call_kwargs["reason"]
    mock_registry.set_idle.assert_called_once_with("reviewer-1")
    assert task.retry_count == 1

    # Should re-queue with feedback
    mock_stream.publish.assert_called_once()
    publish_args = mock_stream.publish.call_args
    assert publish_args[0][0] == "tasks:queue"
    published_msg = publish_args[0][1]
    assert published_msg["retry_feedback"] == "Tests not passing"
    assert published_msg["retry_count"] == "1"


async def test_process_result_qa_failure_escalates_to_redesign(
    orchestrator: PMOrchestrator, mock_db: AsyncMock, mock_registry: AsyncMock, mock_state_machine: AsyncMock
) -> None:
    """QA failure should escalate to redesign when retry_count >= max_retries."""
    task = make_task(status=TaskStatus.review, retry_count=2, max_retries=3)

    result = {
        "task_id": str(task.id),
        "type": "qa",
        "success": "false",
        "passed": "false",
        "feedback": "Still failing tests",
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
    assert call_kwargs["new_status"] == TaskStatus.redesign
    assert "Max retries (3) exceeded" in call_kwargs["reason"]
    assert "Still failing tests" in call_kwargs["reason"]
    mock_registry.set_idle.assert_called_once_with("reviewer-1")
    assert task.retry_count == 3


# -- qa_feedback_history accumulation ------------------------------------------


async def test_qa_feedback_history_accumulates_entries(
    orchestrator: PMOrchestrator, mock_db: AsyncMock, mock_state_machine: AsyncMock
) -> None:
    """qa_feedback_history should accumulate entries across multiple failures."""
    task = make_task(status=TaskStatus.in_progress, retry_count=0, max_retries=3, qa_feedback_history=None)

    # First execution failure
    await orchestrator._handle_execution_failure(task, mock_db, "worker-1", "Compile error")
    assert task.retry_count == 1
    assert task.qa_feedback_history is not None
    assert len(task.qa_feedback_history) == 1
    assert task.qa_feedback_history[0]["type"] == "execution_failure"
    assert task.qa_feedback_history[0]["error"] == "Compile error"
    assert task.qa_feedback_history[0]["attempt"] == 1

    mock_state_machine.transition.reset_mock()

    # Second execution failure on the same task
    await orchestrator._handle_execution_failure(task, mock_db, "worker-1", "Link error")
    assert task.retry_count == 2
    assert task.qa_feedback_history is not None
    assert len(task.qa_feedback_history) == 2
    assert task.qa_feedback_history[1]["type"] == "execution_failure"
    assert task.qa_feedback_history[1]["error"] == "Link error"
    assert task.qa_feedback_history[1]["attempt"] == 2


async def test_qa_feedback_history_accumulates_qa_failures(
    orchestrator: PMOrchestrator,
    mock_db: AsyncMock,
    mock_state_machine: AsyncMock,
    mock_stream: AsyncMock,
) -> None:
    """qa_feedback_history should accumulate QA failure entries."""
    project_id = uuid.uuid4()
    task = make_task(
        status=TaskStatus.review,
        retry_count=0,
        max_retries=3,
        qa_feedback_history=None,
        project_id=project_id,
    )

    with patch("backend.src.core.orchestrator.ProjectRepository") as MockProjectRepo:
        mock_project = MagicMock()
        mock_project.repo_path = "/repos/test"
        mock_project_repo_instance = AsyncMock()
        mock_project_repo_instance.get_by_id = AsyncMock(return_value=mock_project)
        MockProjectRepo.return_value = mock_project_repo_instance

        await orchestrator._handle_qa_failure(task, mock_db, "reviewer-1", "Missing tests")

    assert task.retry_count == 1
    assert task.qa_feedback_history is not None
    assert len(task.qa_feedback_history) == 1
    assert task.qa_feedback_history[0]["type"] == "qa_failure"
    assert task.qa_feedback_history[0]["feedback"] == "Missing tests"
    assert task.qa_feedback_history[0]["attempt"] == 1


async def test_qa_feedback_history_initializes_from_none(
    orchestrator: PMOrchestrator, mock_db: AsyncMock, mock_state_machine: AsyncMock
) -> None:
    """qa_feedback_history should be initialized from None to a list on first failure."""
    task = make_task(status=TaskStatus.in_progress, retry_count=0, max_retries=3, qa_feedback_history=None)
    assert task.qa_feedback_history is None

    await orchestrator._handle_execution_failure(task, mock_db, "worker-1", "Error")

    assert task.qa_feedback_history is not None
    assert isinstance(task.qa_feedback_history, list)
    assert len(task.qa_feedback_history) == 1


# -- _requeue_with_feedback ----------------------------------------------------


async def test_requeue_with_feedback_publishes_message(
    orchestrator: PMOrchestrator, mock_db: AsyncMock, mock_stream: AsyncMock
) -> None:
    """_requeue_with_feedback should publish to tasks:queue with retry_feedback and retry_count."""
    project_id = uuid.uuid4()
    task = make_task(
        status=TaskStatus.in_progress,
        retry_count=2,
        max_retries=3,
        project_id=project_id,
        title="Implement feature",
        branch_name="feat/login",
        worker_prompt="Write the login page",
    )

    with patch("backend.src.core.orchestrator.ProjectRepository") as MockProjectRepo:
        mock_project = MagicMock()
        mock_project.repo_path = "/repos/myproject"
        mock_project_repo_instance = AsyncMock()
        mock_project_repo_instance.get_by_id = AsyncMock(return_value=mock_project)
        MockProjectRepo.return_value = mock_project_repo_instance

        await orchestrator._requeue_with_feedback(task, mock_db, "Fix the failing tests")

    mock_stream.publish.assert_called_once()
    call_args = mock_stream.publish.call_args
    assert call_args[0][0] == "tasks:queue"
    message = call_args[0][1]
    assert message["task_id"] == str(task.id)
    assert message["project_id"] == str(project_id)
    assert message["priority"] == TaskPriority.medium.value
    assert message["title"] == "Implement feature"
    assert message["retry_feedback"] == "Fix the failing tests"
    assert message["retry_count"] == "2"
    assert message["branch_name"] == "feat/login"
    assert message["worker_prompt"] == "Write the login page"
    assert message["repo_path"] == "/repos/myproject"


async def test_requeue_with_feedback_without_optional_fields(
    orchestrator: PMOrchestrator, mock_db: AsyncMock, mock_stream: AsyncMock
) -> None:
    """_requeue_with_feedback should omit branch_name and worker_prompt when not set."""
    project_id = uuid.uuid4()
    task = make_task(
        status=TaskStatus.in_progress,
        retry_count=1,
        project_id=project_id,
        title="Simple task",
        branch_name=None,
        worker_prompt=None,
    )

    with patch("backend.src.core.orchestrator.ProjectRepository") as MockProjectRepo:
        mock_project = MagicMock()
        mock_project.repo_path = "/repos/test"
        mock_project_repo_instance = AsyncMock()
        mock_project_repo_instance.get_by_id = AsyncMock(return_value=mock_project)
        MockProjectRepo.return_value = mock_project_repo_instance

        await orchestrator._requeue_with_feedback(task, mock_db, "Some feedback")

    mock_stream.publish.assert_called_once()
    message = mock_stream.publish.call_args[0][1]
    assert "branch_name" not in message
    assert "worker_prompt" not in message
    assert message["retry_feedback"] == "Some feedback"


# -- _assign_reviewer ----------------------------------------------------------


async def test_assign_reviewer_uses_executor_worker(
    orchestrator: PMOrchestrator, mock_db: AsyncMock, mock_state_machine: AsyncMock
) -> None:
    """_assign_reviewer should always assign the executor worker as reviewer."""
    task = make_task(status=TaskStatus.in_progress)

    await orchestrator._assign_reviewer(task, mock_db, "executor-1")

    mock_state_machine.transition.assert_called_once()
    call_kwargs = mock_state_machine.transition.call_args[1]
    assert call_kwargs["new_status"] == TaskStatus.review
    assert call_kwargs["reviewer_id"] == "executor-1"


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
        mock_repo_instance.count_active_tasks = AsyncMock(return_value=0)
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
        mock_repo_instance.count_active_tasks = AsyncMock(return_value=0)
        MockRepo.return_value = mock_repo_instance

        result = await orchestrator.queue_next(project_id, mock_db)

    assert result is None


async def test_queue_next_returns_none_when_task_already_active(
    orchestrator: PMOrchestrator, mock_state_machine: AsyncMock
) -> None:
    """queue_next should return None when a task is already in progress (sequential constraint)."""
    project_id = uuid.uuid4()
    mock_db = AsyncMock()

    with patch("backend.src.core.orchestrator.TaskRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.count_active_tasks = AsyncMock(return_value=1)
        MockRepo.return_value = mock_repo_instance

        result = await orchestrator.queue_next(project_id, mock_db)

    assert result is None
    mock_state_machine.transition.assert_not_called()


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


# -- _process_escalation: auto-redesign ----------------------------------------


async def test_process_escalation_modify(
    orchestrator: PMOrchestrator, mock_db: AsyncMock, mock_state_machine: AsyncMock, mock_stream: AsyncMock
) -> None:
    """LLM returning modify action should update task prompts and transition to waiting."""
    project_id = uuid.uuid4()
    task = make_task(
        status=TaskStatus.redesign,
        project_id=project_id,
        retry_count=3,
        max_retries=3,
        worker_prompt={"prompt": "old prompt"},
        qa_prompt={"prompt": "old qa"},
        error_message="Build failed",
        qa_feedback_history=[{"type": "execution_failure", "attempt": 3, "error": "Build failed"}],
    )

    msg = {
        "task_id": str(task.id),
        "project_id": str(project_id),
        "_message_id": "esc-1",
    }

    mock_project = MagicMock()
    mock_project.id = project_id
    mock_project.llm_config = {"architect": {"api_key": "test-key", "model": "test-model"}}

    llm_result = {
        "action": "modify",
        "reasoning": "Prompt was unclear",
        "title": "Updated Title",
        "description": "Updated desc",
        "worker_prompt": "New improved prompt",
        "qa_prompt": "New qa checklist",
        "split_tasks": [],
    }

    with (
        patch("backend.src.core.orchestrator.TaskRepository") as MockTaskRepo,
        patch("backend.src.core.orchestrator.ProjectRepository") as MockProjectRepo,
        patch("backend.src.core.orchestrator.create_llm_client_from_project") as mock_create_llm,
        patch("backend.src.core.orchestrator.get_prompt") as mock_get_prompt,
    ):
        MockTaskRepo.return_value = AsyncMock(get_by_id=AsyncMock(return_value=task))
        MockProjectRepo.return_value = AsyncMock(get_by_id=AsyncMock(return_value=mock_project))
        mock_llm_client = AsyncMock()
        mock_llm_client.structured_output = AsyncMock(return_value=llm_result)
        mock_create_llm.return_value = mock_llm_client
        mock_get_prompt.return_value = "mocked prompt {title} {description} {priority} {retry_count} {max_retries} {branch_name} {worker_prompt} {qa_prompt} {failure_history} {error_message}"

        await orchestrator._process_escalation(msg, mock_db)

    # Verify task fields updated
    assert task.title == "Updated Title"
    assert task.description == "Updated desc"
    assert task.worker_prompt == {"prompt": "New improved prompt"}
    assert task.qa_prompt == {"prompt": "New qa checklist"}
    assert task.retry_count == 0
    assert task.qa_feedback_history is None
    assert task.error_message is None

    # Verify Redis counter incremented
    mock_stream.redis.incr.assert_called_once_with(f"task:{task.id}:auto_redesign_count")
    mock_stream.redis.expire.assert_called_once()

    # Verify transition to waiting
    mock_state_machine.transition.assert_called_once()
    call_kwargs = mock_state_machine.transition.call_args[1]
    assert call_kwargs["new_status"] == TaskStatus.waiting
    assert "Auto-redesigned" in call_kwargs["reason"]

    # Verify board event
    mock_stream.publish_board_event.assert_called()
    event_call = mock_stream.publish_board_event.call_args
    assert event_call[0][0] == "auto_redesign_applied"
    assert event_call[0][1]["action"] == "modify"


async def test_process_escalation_delete(
    orchestrator: PMOrchestrator, mock_db: AsyncMock, mock_state_machine: AsyncMock, mock_stream: AsyncMock
) -> None:
    """LLM returning delete action should transition task to done."""
    project_id = uuid.uuid4()
    task = make_task(status=TaskStatus.redesign, project_id=project_id)

    msg = {"task_id": str(task.id), "project_id": str(project_id), "_message_id": "esc-2"}

    mock_project = MagicMock()
    mock_project.id = project_id
    mock_project.llm_config = {"architect": {"api_key": "test-key"}}

    llm_result = {"action": "delete", "reasoning": "Task is obsolete", "split_tasks": []}

    with (
        patch("backend.src.core.orchestrator.TaskRepository") as MockTaskRepo,
        patch("backend.src.core.orchestrator.ProjectRepository") as MockProjectRepo,
        patch("backend.src.core.orchestrator.create_llm_client_from_project") as mock_create_llm,
        patch("backend.src.core.orchestrator.get_prompt") as mock_get_prompt,
    ):
        MockTaskRepo.return_value = AsyncMock(get_by_id=AsyncMock(return_value=task))
        MockProjectRepo.return_value = AsyncMock(get_by_id=AsyncMock(return_value=mock_project))
        mock_llm_client = AsyncMock()
        mock_llm_client.structured_output = AsyncMock(return_value=llm_result)
        mock_create_llm.return_value = mock_llm_client
        mock_get_prompt.return_value = "mocked {title} {description} {priority} {retry_count} {max_retries} {branch_name} {worker_prompt} {qa_prompt} {failure_history} {error_message}"

        await orchestrator._process_escalation(msg, mock_db)

    mock_state_machine.transition.assert_called_once()
    call_kwargs = mock_state_machine.transition.call_args[1]
    assert call_kwargs["new_status"] == TaskStatus.done
    assert "delete" in call_kwargs["reason"].lower()

    # Verify Redis counter incremented
    mock_stream.redis.incr.assert_called_once_with(f"task:{task.id}:auto_redesign_count")


async def test_process_escalation_split(
    orchestrator: PMOrchestrator, mock_db: AsyncMock, mock_state_machine: AsyncMock, mock_stream: AsyncMock
) -> None:
    """LLM returning split action should mark original done and create sub-tasks."""
    project_id = uuid.uuid4()
    phase_id = uuid.uuid4()
    task = make_task(
        status=TaskStatus.redesign,
        project_id=project_id,
        phase_id=phase_id,
        branch_name="feat/test",
    )

    msg = {"task_id": str(task.id), "project_id": str(project_id), "_message_id": "esc-3"}

    mock_project = MagicMock()
    mock_project.id = project_id
    mock_project.llm_config = {"architect": {"api_key": "test-key"}}

    llm_result = {
        "action": "split",
        "reasoning": "Task too large",
        "split_tasks": [
            {"title": "Sub-task 1", "description": "First part", "priority": "high", "worker_prompt": "Do A", "qa_prompt": "Check A"},
            {"title": "Sub-task 2", "description": "Second part", "priority": "medium", "worker_prompt": "Do B", "qa_prompt": "Check B"},
        ],
    }

    with (
        patch("backend.src.core.orchestrator.TaskRepository") as MockTaskRepo,
        patch("backend.src.core.orchestrator.ProjectRepository") as MockProjectRepo,
        patch("backend.src.core.orchestrator.create_llm_client_from_project") as mock_create_llm,
        patch("backend.src.core.orchestrator.get_prompt") as mock_get_prompt,
    ):
        MockTaskRepo.return_value = AsyncMock(get_by_id=AsyncMock(return_value=task))
        MockProjectRepo.return_value = AsyncMock(get_by_id=AsyncMock(return_value=mock_project))
        mock_llm_client = AsyncMock()
        mock_llm_client.structured_output = AsyncMock(return_value=llm_result)
        mock_create_llm.return_value = mock_llm_client
        mock_get_prompt.return_value = "mocked {title} {description} {priority} {retry_count} {max_retries} {branch_name} {worker_prompt} {qa_prompt} {failure_history} {error_message}"

        await orchestrator._process_escalation(msg, mock_db)

    # Original task should be transitioned to done
    mock_state_machine.transition.assert_called_once()
    call_kwargs = mock_state_machine.transition.call_args[1]
    assert call_kwargs["new_status"] == TaskStatus.done
    assert "Split into 2 sub-tasks" in call_kwargs["reason"]

    # Two new tasks should be added to db
    assert mock_db.add.call_count == 2
    added_tasks = [call[0][0] for call in mock_db.add.call_args_list]
    assert added_tasks[0].title == "Sub-task 1"
    assert added_tasks[0].project_id == project_id
    assert added_tasks[0].phase_id == phase_id
    assert added_tasks[0].branch_name == "feat/test"
    assert added_tasks[1].title == "Sub-task 2"

    # Verify Redis counter incremented
    mock_stream.redis.incr.assert_called_once_with(f"task:{task.id}:auto_redesign_count")


async def test_process_escalation_max_auto_redesigns(
    orchestrator: PMOrchestrator, mock_db: AsyncMock, mock_state_machine: AsyncMock, mock_stream: AsyncMock
) -> None:
    """When Redis auto_redesign_count >= max, should skip LLM and publish failure event."""
    project_id = uuid.uuid4()
    task = make_task(status=TaskStatus.redesign, project_id=project_id)

    msg = {"task_id": str(task.id), "project_id": str(project_id), "_message_id": "esc-4"}

    # Set Redis counter to max
    mock_stream.redis.get = AsyncMock(return_value=b"2")

    with (
        patch("backend.src.core.orchestrator.TaskRepository") as MockTaskRepo,
        patch("backend.src.core.orchestrator.settings") as mock_settings,
    ):
        mock_settings.max_auto_redesigns = 2
        MockTaskRepo.return_value = AsyncMock(get_by_id=AsyncMock(return_value=task))

        await orchestrator._process_escalation(msg, mock_db)

    # No LLM call, no transition
    mock_state_machine.transition.assert_not_called()

    # Should publish failure event
    mock_stream.publish_board_event.assert_called_once()
    event_call = mock_stream.publish_board_event.call_args
    assert event_call[0][0] == "auto_redesign_failed"
    assert "Max auto-redesign attempts" in event_call[0][1]["reason"]


async def test_process_escalation_llm_error(
    orchestrator: PMOrchestrator, mock_db: AsyncMock, mock_state_machine: AsyncMock, mock_stream: AsyncMock
) -> None:
    """When LLM call fails, should publish failure event and leave task in redesign."""
    from backend.src.core.llm_client import LLMError

    project_id = uuid.uuid4()
    task = make_task(status=TaskStatus.redesign, project_id=project_id)

    msg = {"task_id": str(task.id), "project_id": str(project_id), "_message_id": "esc-5"}

    mock_project = MagicMock()
    mock_project.id = project_id
    mock_project.llm_config = {"architect": {"api_key": "test-key"}}

    with (
        patch("backend.src.core.orchestrator.TaskRepository") as MockTaskRepo,
        patch("backend.src.core.orchestrator.ProjectRepository") as MockProjectRepo,
        patch("backend.src.core.orchestrator.create_llm_client_from_project") as mock_create_llm,
        patch("backend.src.core.orchestrator.get_prompt") as mock_get_prompt,
    ):
        MockTaskRepo.return_value = AsyncMock(get_by_id=AsyncMock(return_value=task))
        MockProjectRepo.return_value = AsyncMock(get_by_id=AsyncMock(return_value=mock_project))
        mock_llm_client = AsyncMock()
        mock_llm_client.structured_output = AsyncMock(side_effect=LLMError("API timeout"))
        mock_create_llm.return_value = mock_llm_client
        mock_get_prompt.return_value = "mocked {title} {description} {priority} {retry_count} {max_retries} {branch_name} {worker_prompt} {qa_prompt} {failure_history} {error_message}"

        await orchestrator._process_escalation(msg, mock_db)

    # No state transition
    mock_state_machine.transition.assert_not_called()

    # Should publish failure event
    mock_stream.publish_board_event.assert_called_once()
    event_call = mock_stream.publish_board_event.call_args
    assert event_call[0][0] == "auto_redesign_failed"
    assert "LLM error" in event_call[0][1]["reason"]

    # Redis counter should NOT be incremented
    mock_stream.redis.incr.assert_not_called()


async def test_process_escalation_skips_other_project(
    orchestrator: PMOrchestrator, mock_db: AsyncMock, mock_state_machine: AsyncMock
) -> None:
    """Task not in redesign status should be skipped."""
    project_id = uuid.uuid4()
    task = make_task(status=TaskStatus.done, project_id=project_id)

    msg = {"task_id": str(task.id), "project_id": str(project_id), "_message_id": "esc-6"}

    with patch("backend.src.core.orchestrator.TaskRepository") as MockTaskRepo:
        MockTaskRepo.return_value = AsyncMock(get_by_id=AsyncMock(return_value=task))

        await orchestrator._process_escalation(msg, mock_db)

    # No transition since task is not in redesign status
    mock_state_machine.transition.assert_not_called()


async def test_process_escalation_task_not_found(
    orchestrator: PMOrchestrator, mock_db: AsyncMock, mock_state_machine: AsyncMock
) -> None:
    """Missing task should be skipped without error."""
    msg = {"task_id": str(uuid.uuid4()), "project_id": str(uuid.uuid4()), "_message_id": "esc-7"}

    with patch("backend.src.core.orchestrator.TaskRepository") as MockTaskRepo:
        MockTaskRepo.return_value = AsyncMock(get_by_id=AsyncMock(return_value=None))

        await orchestrator._process_escalation(msg, mock_db)

    mock_state_machine.transition.assert_not_called()


async def test_redesign_prompt_formats_correctly() -> None:
    """The redesign prompt template should format with all placeholders."""
    from backend.src.prompts.loader import get_prompt

    prompt_template = get_prompt("architect", "redesign")
    formatted = prompt_template.format(
        title="Test Task",
        description="A test task",
        priority="high",
        retry_count=3,
        max_retries=3,
        branch_name="feat/test",
        worker_prompt="Do the thing",
        qa_prompt="Check the thing",
        failure_history="[]",
        error_message="Build failed",
    )
    assert "Test Task" in formatted
    assert "Build failed" in formatted
    assert "Do the thing" in formatted
    # Ensure literal braces are rendered (not template syntax)
    assert '"action"' in formatted


async def test_process_escalation_environment_error_skips_llm(
    orchestrator: PMOrchestrator, mock_db: AsyncMock, mock_state_machine: AsyncMock, mock_stream: AsyncMock
) -> None:
    """Deterministic environment errors should skip auto-redesign and publish failure immediately."""
    project_id = uuid.uuid4()
    task = make_task(
        status=TaskStatus.redesign,
        project_id=project_id,
        error_message="[WinError 2] 지정된 파일을 찾을 수 없습니다",
    )

    msg = {"task_id": str(task.id), "project_id": str(project_id), "_message_id": "esc-env"}

    with patch("backend.src.core.orchestrator.TaskRepository") as MockTaskRepo:
        MockTaskRepo.return_value = AsyncMock(get_by_id=AsyncMock(return_value=task))
        await orchestrator._process_escalation(msg, mock_db)

    # No LLM call, no transition
    mock_state_machine.transition.assert_not_called()
    # Redis counter should not be touched
    mock_stream.redis.incr.assert_not_called()
    # Should publish failure event with environment error reason
    mock_stream.publish_board_event.assert_called_once()
    event_call = mock_stream.publish_board_event.call_args
    assert event_call[0][0] == "auto_redesign_failed"
    assert "Environment error" in event_call[0][1]["reason"]


def test_is_environment_error() -> None:
    """_is_environment_error should detect known deterministic error patterns."""
    assert PMOrchestrator._is_environment_error("[WinError 2] File not found") is True
    assert PMOrchestrator._is_environment_error("FileNotFoundError: No such file") is True
    assert PMOrchestrator._is_environment_error("ENOENT: no such file or directory") is True
    assert PMOrchestrator._is_environment_error("PermissionError: access denied") is True
    assert PMOrchestrator._is_environment_error("command not found: claude") is True
    assert PMOrchestrator._is_environment_error("Build failed: tests not passing") is False
    assert PMOrchestrator._is_environment_error("TypeError: cannot read property") is False
    assert PMOrchestrator._is_environment_error(None) is False
    assert PMOrchestrator._is_environment_error("") is False
