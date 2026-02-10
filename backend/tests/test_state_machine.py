from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.core.state_machine import TaskStateMachine
from backend.src.models import Task, TaskHistory, TaskPriority, TaskStatus


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def state_machine() -> TaskStateMachine:
    return TaskStateMachine()


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_stream() -> AsyncMock:
    manager = AsyncMock()
    manager.publish = AsyncMock(return_value="mock-id")
    manager.publish_board_event = AsyncMock()
    return manager


# ── Helpers ──────────────────────────────────────────────────────────────


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
        commit_hash=kwargs.get("commit_hash", None),
        qa_result=kwargs.get("qa_result", None),
        output_path=kwargs.get("output_path", None),
        error_message=kwargs.get("error_message", None),
        started_at=None,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )


# ── can_transition (pure logic, no mocking) ─────────────────────────────


def test_can_transition_valid(state_machine: TaskStateMachine) -> None:
    assert state_machine.can_transition(TaskStatus.waiting, TaskStatus.ready) is True


def test_can_transition_invalid(state_machine: TaskStateMachine) -> None:
    assert state_machine.can_transition(TaskStatus.waiting, TaskStatus.done) is False


def test_can_transition_all_valid_paths(state_machine: TaskStateMachine) -> None:
    valid_pairs = [
        (TaskStatus.waiting, TaskStatus.ready),
        (TaskStatus.ready, TaskStatus.queued),
        (TaskStatus.queued, TaskStatus.in_progress),
        (TaskStatus.in_progress, TaskStatus.review),
        (TaskStatus.in_progress, TaskStatus.rejected),
        (TaskStatus.review, TaskStatus.done),
        (TaskStatus.review, TaskStatus.rejected),
        (TaskStatus.done, TaskStatus.rejected),
        (TaskStatus.rejected, TaskStatus.ready),
        (TaskStatus.waiting, TaskStatus.blocked),
        (TaskStatus.blocked, TaskStatus.ready),
    ]
    for from_s, to_s in valid_pairs:
        assert state_machine.can_transition(from_s, to_s) is True, f"{from_s} -> {to_s} should be valid"


# ── Valid transitions ────────────────────────────────────────────────────


async def test_valid_transition_waiting_to_ready(
    state_machine: TaskStateMachine, mock_db: AsyncMock, mock_stream: AsyncMock
) -> None:
    task = make_task(status=TaskStatus.waiting)
    result = await state_machine.transition(
        task, TaskStatus.ready, reason="deps met", actor="system", db_session=mock_db, stream_manager=mock_stream
    )
    assert result.status == TaskStatus.ready
    assert result.version == 2
    # Verify history was added to session
    mock_db.add.assert_called_once()
    # Verify board event was published
    mock_stream.publish_board_event.assert_called_once()


async def test_valid_transition_ready_to_queued(
    state_machine: TaskStateMachine, mock_db: AsyncMock, mock_stream: AsyncMock
) -> None:
    task = make_task(status=TaskStatus.ready)
    result = await state_machine.transition(task, TaskStatus.queued, db_session=mock_db, stream_manager=mock_stream)
    assert result.status == TaskStatus.queued
    # _on_queued publishes to "tasks:queue"
    mock_stream.publish.assert_called_once()
    call_args = mock_stream.publish.call_args
    assert call_args[0][0] == "tasks:queue"


async def test_valid_transition_queued_to_in_progress(
    state_machine: TaskStateMachine, mock_db: AsyncMock, mock_stream: AsyncMock
) -> None:
    task = make_task(status=TaskStatus.queued)
    worker_id = uuid.uuid4()
    result = await state_machine.transition(
        task, TaskStatus.in_progress, db_session=mock_db, stream_manager=mock_stream, worker_id=str(worker_id)
    )
    assert result.status == TaskStatus.in_progress
    assert result.started_at is not None
    assert result.worker_id == worker_id


async def test_valid_transition_in_progress_to_review(
    state_machine: TaskStateMachine, mock_db: AsyncMock, mock_stream: AsyncMock
) -> None:
    task = make_task(status=TaskStatus.in_progress)
    result = await state_machine.transition(task, TaskStatus.review, db_session=mock_db, stream_manager=mock_stream)
    assert result.status == TaskStatus.review


async def test_valid_transition_review_to_done(
    state_machine: TaskStateMachine, mock_db: AsyncMock, mock_stream: AsyncMock
) -> None:
    task = make_task(status=TaskStatus.review)

    with patch("backend.src.core.state_machine.TaskRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.find_waiting_dependents = AsyncMock(return_value=[])
        MockRepo.return_value = mock_repo_instance

        result = await state_machine.transition(task, TaskStatus.done, db_session=mock_db, stream_manager=mock_stream)

    assert result.status == TaskStatus.done
    assert result.completed_at is not None


async def test_valid_transition_review_to_rejected(
    state_machine: TaskStateMachine, mock_db: AsyncMock, mock_stream: AsyncMock
) -> None:
    task = make_task(status=TaskStatus.review)

    with patch("backend.src.core.state_machine.TaskRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.find_waiting_dependents = AsyncMock(return_value=[])
        MockRepo.return_value = mock_repo_instance

        result = await state_machine.transition(
            task, TaskStatus.rejected, db_session=mock_db, stream_manager=mock_stream, reason="Quality issues"
        )

    assert result.status == TaskStatus.rejected


async def test_valid_transition_rejected_to_ready(
    state_machine: TaskStateMachine, mock_db: AsyncMock, mock_stream: AsyncMock
) -> None:
    task = make_task(status=TaskStatus.rejected)
    result = await state_machine.transition(task, TaskStatus.ready, db_session=mock_db, stream_manager=mock_stream)
    assert result.status == TaskStatus.ready


async def test_valid_transition_done_to_rejected(
    state_machine: TaskStateMachine, mock_db: AsyncMock, mock_stream: AsyncMock
) -> None:
    task = make_task(status=TaskStatus.done)

    with patch("backend.src.core.state_machine.TaskRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.find_waiting_dependents = AsyncMock(return_value=[])
        MockRepo.return_value = mock_repo_instance

        result = await state_machine.transition(
            task, TaskStatus.rejected, db_session=mock_db, stream_manager=mock_stream, reason="Rollback needed"
        )

    assert result.status == TaskStatus.rejected


# ── Invalid transitions ──────────────────────────────────────────────────


async def test_invalid_transition_waiting_to_done(
    state_machine: TaskStateMachine, mock_db: AsyncMock, mock_stream: AsyncMock
) -> None:
    task = make_task(status=TaskStatus.waiting)
    with pytest.raises(ValueError, match="Invalid transition"):
        await state_machine.transition(task, TaskStatus.done, db_session=mock_db, stream_manager=mock_stream)


async def test_invalid_transition_done_to_queued(
    state_machine: TaskStateMachine, mock_db: AsyncMock, mock_stream: AsyncMock
) -> None:
    task = make_task(status=TaskStatus.done)
    with pytest.raises(ValueError, match="Invalid transition"):
        await state_machine.transition(task, TaskStatus.queued, db_session=mock_db, stream_manager=mock_stream)


# ── check_dependencies_met (mock TaskRepository) ────────────────────────


async def test_check_dependencies_met_all_done(state_machine: TaskStateMachine, mock_db: AsyncMock) -> None:
    task = make_task()
    with patch("backend.src.core.state_machine.TaskRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.check_dependencies_met = AsyncMock(return_value=True)
        MockRepo.return_value = mock_repo_instance

        result = await state_machine.check_dependencies_met(task, mock_db)
        assert result is True


async def test_check_dependencies_met_not_done(state_machine: TaskStateMachine, mock_db: AsyncMock) -> None:
    task = make_task()
    with patch("backend.src.core.state_machine.TaskRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.check_dependencies_met = AsyncMock(return_value=False)
        MockRepo.return_value = mock_repo_instance

        result = await state_machine.check_dependencies_met(task, mock_db)
        assert result is False


# ── promote_dependents (mock TaskRepository) ─────────────────────────────


async def test_promote_dependents_on_done(
    state_machine: TaskStateMachine, mock_db: AsyncMock, mock_stream: AsyncMock
) -> None:
    task = make_task(status=TaskStatus.review)
    waiting_task = make_task(status=TaskStatus.waiting)

    with patch("backend.src.core.state_machine.TaskRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.find_waiting_dependents = AsyncMock(return_value=[waiting_task])
        mock_repo_instance.find_blocked_dependents = AsyncMock(return_value=[])
        mock_repo_instance.check_dependencies_met = AsyncMock(return_value=True)
        MockRepo.return_value = mock_repo_instance

        result = await state_machine.transition(task, TaskStatus.done, db_session=mock_db, stream_manager=mock_stream)

    assert result.status == TaskStatus.done
    assert result.completed_at is not None
    # The waiting dependent should have been promoted
    assert waiting_task.status == TaskStatus.ready
    assert waiting_task.version == 2


# ── Version increment ────────────────────────────────────────────────────


async def test_version_increment(state_machine: TaskStateMachine, mock_db: AsyncMock, mock_stream: AsyncMock) -> None:
    task = make_task(status=TaskStatus.waiting, version=1)
    await state_machine.transition(task, TaskStatus.ready, db_session=mock_db, stream_manager=mock_stream)
    assert task.version == 2


async def test_version_increments_multiple_times(
    state_machine: TaskStateMachine, mock_db: AsyncMock, mock_stream: AsyncMock
) -> None:
    task = make_task(status=TaskStatus.waiting, version=1)
    await state_machine.transition(task, TaskStatus.ready, db_session=mock_db, stream_manager=mock_stream)
    assert task.version == 2
    await state_machine.transition(task, TaskStatus.queued, db_session=mock_db, stream_manager=mock_stream)
    assert task.version == 3


# ── History recording ────────────────────────────────────────────────────


async def test_task_history_recorded(
    state_machine: TaskStateMachine, mock_db: AsyncMock, mock_stream: AsyncMock
) -> None:
    task = make_task(status=TaskStatus.waiting)
    await state_machine.transition(
        task, TaskStatus.ready, actor="test-user", reason="deps met", db_session=mock_db, stream_manager=mock_stream
    )
    # Verify db_session.add was called with a TaskHistory object
    mock_db.add.assert_called_once()
    added_obj = mock_db.add.call_args[0][0]
    assert isinstance(added_obj, TaskHistory)
    assert added_obj.from_status == "waiting"
    assert added_obj.to_status == "ready"
    assert added_obj.actor == "test-user"
    assert added_obj.reason == "deps met"


# ── Side effects ─────────────────────────────────────────────────────────


async def test_on_queued_publishes_to_stream(
    state_machine: TaskStateMachine, mock_db: AsyncMock, mock_stream: AsyncMock
) -> None:
    task = make_task(status=TaskStatus.ready)
    await state_machine.transition(task, TaskStatus.queued, db_session=mock_db, stream_manager=mock_stream)
    mock_stream.publish.assert_called_once()
    call_args = mock_stream.publish.call_args
    assert call_args[0][0] == "tasks:queue"
    payload = call_args[0][1]
    assert payload["task_id"] == str(task.id)
    assert payload["priority"] == task.priority.value


async def test_on_in_progress_sets_started_at(
    state_machine: TaskStateMachine, mock_db: AsyncMock, mock_stream: AsyncMock
) -> None:
    task = make_task(status=TaskStatus.queued)
    assert task.started_at is None
    await state_machine.transition(task, TaskStatus.in_progress, db_session=mock_db, stream_manager=mock_stream)
    assert task.started_at is not None


async def test_on_in_progress_sets_worker_id(
    state_machine: TaskStateMachine, mock_db: AsyncMock, mock_stream: AsyncMock
) -> None:
    task = make_task(status=TaskStatus.queued)
    worker_id = uuid.uuid4()
    await state_machine.transition(
        task, TaskStatus.in_progress, db_session=mock_db, stream_manager=mock_stream, worker_id=str(worker_id)
    )
    assert task.worker_id == worker_id


async def test_on_done_sets_completed_at(
    state_machine: TaskStateMachine, mock_db: AsyncMock, mock_stream: AsyncMock
) -> None:
    task = make_task(status=TaskStatus.review)
    assert task.completed_at is None

    with patch("backend.src.core.state_machine.TaskRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.find_waiting_dependents = AsyncMock(return_value=[])
        MockRepo.return_value = mock_repo_instance

        await state_machine.transition(task, TaskStatus.done, db_session=mock_db, stream_manager=mock_stream)

    assert task.completed_at is not None


async def test_on_rejected_sets_error_message(
    state_machine: TaskStateMachine, mock_db: AsyncMock, mock_stream: AsyncMock
) -> None:
    task = make_task(status=TaskStatus.in_progress)
    # Call _on_rejected directly because the `reason` named param in transition()
    # is consumed for history recording and does not propagate to side-effect kwargs.
    with patch("backend.src.core.state_machine.TaskRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.find_waiting_dependents = AsyncMock(return_value=[])
        MockRepo.return_value = mock_repo_instance

        await state_machine._on_rejected(task, db_session=mock_db, stream_manager=mock_stream, reason="Build failed")

    assert task.error_message == "Build failed"


# ── GitOps + PromptSigner integration tests ──────────────────────────────


async def test_on_queued_with_prompt_signer_signs_worker_prompt(
    mock_db: AsyncMock, mock_stream: AsyncMock,
) -> None:
    mock_signer = AsyncMock()
    mock_signer.sign = lambda prompt: {"prompt": prompt, "signature": "test-sig", "nonce": "test-nonce", "timestamp": 0}
    sm = TaskStateMachine(prompt_signer=mock_signer)
    task = make_task(status=TaskStatus.ready, worker_prompt={"content": "test"})

    await sm.transition(task, TaskStatus.queued, db_session=mock_db, stream_manager=mock_stream)

    call_args = mock_stream.publish.call_args
    payload = call_args[0][1]
    assert "signed_worker_prompt" in payload
    assert payload["signed_worker_prompt"]["signature"] == "test-sig"


async def test_on_queued_without_prompt_signer_no_signature(
    mock_db: AsyncMock, mock_stream: AsyncMock,
) -> None:
    sm = TaskStateMachine()
    task = make_task(status=TaskStatus.ready, worker_prompt={"content": "test"})

    await sm.transition(task, TaskStatus.queued, db_session=mock_db, stream_manager=mock_stream)

    call_args = mock_stream.publish.call_args
    payload = call_args[0][1]
    assert "signed_worker_prompt" not in payload


async def test_on_review_with_prompt_signer_signs_qa_prompt(
    mock_db: AsyncMock, mock_stream: AsyncMock,
) -> None:
    mock_signer = AsyncMock()
    mock_signer.sign = lambda prompt: {"prompt": prompt, "signature": "qa-sig", "nonce": "qa-nonce", "timestamp": 0}
    sm = TaskStateMachine(prompt_signer=mock_signer)
    task = make_task(status=TaskStatus.in_progress, qa_prompt={"content": "qa test"})

    await sm.transition(task, TaskStatus.review, db_session=mock_db, stream_manager=mock_stream)

    call_args = mock_stream.publish.call_args
    payload = call_args[0][1]
    assert "signed_qa_prompt" in payload
    assert payload["signed_qa_prompt"]["signature"] == "qa-sig"


async def test_on_review_without_prompt_signer_no_signature(
    mock_db: AsyncMock, mock_stream: AsyncMock,
) -> None:
    sm = TaskStateMachine()
    task = make_task(status=TaskStatus.in_progress, qa_prompt={"content": "qa test"})

    await sm.transition(task, TaskStatus.review, db_session=mock_db, stream_manager=mock_stream)

    call_args = mock_stream.publish.call_args
    payload = call_args[0][1]
    assert "signed_qa_prompt" not in payload


async def test_on_done_with_git_ops_commits(
    mock_db: AsyncMock, mock_stream: AsyncMock,
) -> None:
    mock_git = AsyncMock()
    mock_git.commit_task = AsyncMock(return_value="abc123hash")
    sm = TaskStateMachine(git_ops=mock_git)
    task = make_task(status=TaskStatus.review, branch_name="feature/test")

    with patch("backend.src.core.state_machine.TaskRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.find_waiting_dependents = AsyncMock(return_value=[])
        MockRepo.return_value = mock_repo_instance

        await sm.transition(task, TaskStatus.done, db_session=mock_db, stream_manager=mock_stream)

    mock_git.commit_task.assert_called_once_with(str(task.id), task.title, "feature/test")
    assert task.commit_hash == "abc123hash"
    assert task.status == TaskStatus.done


async def test_on_done_without_git_ops_no_commit(
    mock_db: AsyncMock, mock_stream: AsyncMock,
) -> None:
    sm = TaskStateMachine()
    task = make_task(status=TaskStatus.review, branch_name="feature/test")

    with patch("backend.src.core.state_machine.TaskRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.find_waiting_dependents = AsyncMock(return_value=[])
        MockRepo.return_value = mock_repo_instance

        await sm.transition(task, TaskStatus.done, db_session=mock_db, stream_manager=mock_stream)

    assert task.commit_hash is None
    assert task.status == TaskStatus.done


async def test_on_done_git_ops_failure_still_completes(
    mock_db: AsyncMock, mock_stream: AsyncMock,
) -> None:
    mock_git = AsyncMock()
    mock_git.commit_task = AsyncMock(side_effect=RuntimeError("git failed"))
    sm = TaskStateMachine(git_ops=mock_git)
    task = make_task(status=TaskStatus.review, branch_name="feature/test")

    with patch("backend.src.core.state_machine.TaskRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.find_waiting_dependents = AsyncMock(return_value=[])
        MockRepo.return_value = mock_repo_instance

        await sm.transition(task, TaskStatus.done, db_session=mock_db, stream_manager=mock_stream)

    assert task.status == TaskStatus.done
    assert task.completed_at is not None
    assert task.commit_hash is None


async def test_on_rejected_with_git_ops_reverts_commit(
    mock_db: AsyncMock, mock_stream: AsyncMock,
) -> None:
    mock_git = AsyncMock()
    mock_git.revert_task = AsyncMock()
    sm = TaskStateMachine(git_ops=mock_git)
    task = make_task(status=TaskStatus.in_progress, commit_hash="abc123")

    with patch("backend.src.core.state_machine.TaskRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.find_waiting_dependents = AsyncMock(return_value=[])
        MockRepo.return_value = mock_repo_instance

        await sm.transition(
            task, TaskStatus.rejected, db_session=mock_db, stream_manager=mock_stream, reason="Bad code"
        )

    mock_git.revert_task.assert_called_once_with("abc123")
    assert task.commit_hash is None
    assert task.status == TaskStatus.rejected


async def test_on_rejected_without_commit_hash_no_revert(
    mock_db: AsyncMock, mock_stream: AsyncMock,
) -> None:
    mock_git = AsyncMock()
    mock_git.revert_task = AsyncMock()
    sm = TaskStateMachine(git_ops=mock_git)
    task = make_task(status=TaskStatus.in_progress)

    with patch("backend.src.core.state_machine.TaskRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.find_waiting_dependents = AsyncMock(return_value=[])
        MockRepo.return_value = mock_repo_instance

        await sm.transition(
            task, TaskStatus.rejected, db_session=mock_db, stream_manager=mock_stream, reason="Bad code"
        )

    mock_git.revert_task.assert_not_called()
    assert task.status == TaskStatus.rejected


async def test_on_rejected_git_ops_failure_still_rejects(
    mock_db: AsyncMock, mock_stream: AsyncMock,
) -> None:
    mock_git = AsyncMock()
    mock_git.revert_task = AsyncMock(side_effect=RuntimeError("revert failed"))
    sm = TaskStateMachine(git_ops=mock_git)
    task = make_task(status=TaskStatus.in_progress, commit_hash="abc123")

    with patch("backend.src.core.state_machine.TaskRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.find_waiting_dependents = AsyncMock(return_value=[])
        MockRepo.return_value = mock_repo_instance

        await sm._on_rejected(
            task, db_session=mock_db, stream_manager=mock_stream, reason="Bad code"
        )

    assert task.error_message == "Bad code"
    # commit_hash is NOT cleared because revert_task raised RuntimeError
    assert task.commit_hash == "abc123"


# ── BLOCKED state tests ───────────────────────────────────────────────────


def test_can_transition_waiting_to_blocked(state_machine: TaskStateMachine) -> None:
    assert state_machine.can_transition(TaskStatus.waiting, TaskStatus.blocked) is True


def test_can_transition_blocked_to_ready(state_machine: TaskStateMachine) -> None:
    assert state_machine.can_transition(TaskStatus.blocked, TaskStatus.ready) is True


def test_cannot_transition_blocked_to_done(state_machine: TaskStateMachine) -> None:
    assert state_machine.can_transition(TaskStatus.blocked, TaskStatus.done) is False


def test_cannot_transition_blocked_to_queued(state_machine: TaskStateMachine) -> None:
    assert state_machine.can_transition(TaskStatus.blocked, TaskStatus.queued) is False


async def test_valid_transition_waiting_to_blocked(
    state_machine: TaskStateMachine, mock_db: AsyncMock, mock_stream: AsyncMock
) -> None:
    task = make_task(status=TaskStatus.waiting)
    result = await state_machine.transition(
        task, TaskStatus.blocked, reason="dependency rejected", actor="system",
        db_session=mock_db, stream_manager=mock_stream,
    )
    assert result.status == TaskStatus.blocked
    assert result.version == 2


async def test_valid_transition_blocked_to_ready(
    state_machine: TaskStateMachine, mock_db: AsyncMock, mock_stream: AsyncMock
) -> None:
    task = make_task(status=TaskStatus.blocked)
    result = await state_machine.transition(
        task, TaskStatus.ready, reason="blocker resolved", actor="system",
        db_session=mock_db, stream_manager=mock_stream,
    )
    assert result.status == TaskStatus.ready
    assert result.version == 2


async def test_on_rejected_blocks_waiting_dependents(
    state_machine: TaskStateMachine, mock_db: AsyncMock, mock_stream: AsyncMock
) -> None:
    task = make_task(status=TaskStatus.in_progress)
    waiting_dep = make_task(status=TaskStatus.waiting)

    with patch("backend.src.core.state_machine.TaskRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.find_waiting_dependents = AsyncMock(return_value=[waiting_dep])
        MockRepo.return_value = mock_repo_instance

        await state_machine.transition(
            task, TaskStatus.rejected, db_session=mock_db, stream_manager=mock_stream, reason="Bad code"
        )

    assert task.status == TaskStatus.rejected
    assert waiting_dep.status == TaskStatus.blocked
    assert waiting_dep.version == 2


async def test_on_done_promotes_blocked_dependents(
    state_machine: TaskStateMachine, mock_db: AsyncMock, mock_stream: AsyncMock
) -> None:
    task = make_task(status=TaskStatus.review)
    blocked_dep = make_task(status=TaskStatus.blocked)

    with patch("backend.src.core.state_machine.TaskRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.find_waiting_dependents = AsyncMock(return_value=[])
        mock_repo_instance.find_blocked_dependents = AsyncMock(return_value=[blocked_dep])
        mock_repo_instance.check_dependencies_met = AsyncMock(return_value=True)
        MockRepo.return_value = mock_repo_instance

        await state_machine.transition(task, TaskStatus.done, db_session=mock_db, stream_manager=mock_stream)

    assert task.status == TaskStatus.done
    assert blocked_dep.status == TaskStatus.ready
    assert blocked_dep.version == 2
