import json
from unittest.mock import AsyncMock, patch

import pytest

from worker.agent import WorkerAgent
from worker.config import WorkerConfig
from worker.consumer import TaskConsumer
from worker.executors.base import BaseExecutor, ExecutionResult, ReviewResult


@pytest.fixture
def config() -> WorkerConfig:
    return WorkerConfig(
        server_url="http://test-server:8000",
        redis_url="redis://localhost:6379",
        executor_type="claude-code",
    )


@pytest.fixture
def agent(config: WorkerConfig) -> WorkerAgent:
    a = WorkerAgent(config)
    a.worker_id = "test-worker-id"
    a.token = "test-token"
    a.streams = {
        "tasks_queue": "tasks:queue",
        "tasks_results": "tasks:results",
        "tasks_qa": "tasks:qa",
    }
    a.consumer_groups = {
        "workers": "workers",
        "reviewers": "reviewers",
    }
    return a


@pytest.fixture
def mock_redis() -> AsyncMock:
    r = AsyncMock()
    r.xadd = AsyncMock()
    r.xack = AsyncMock()
    r.xreadgroup = AsyncMock(return_value=[])
    return r


@pytest.fixture
def mock_executor() -> AsyncMock:
    executor = AsyncMock(spec=BaseExecutor)
    return executor


@pytest.fixture
def consumer(mock_redis: AsyncMock, agent: WorkerAgent, mock_executor: AsyncMock) -> TaskConsumer:
    return TaskConsumer(mock_redis, agent, mock_executor)


class TestProcessTask:
    async def test_process_task_calls_executor_and_publishes_result(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, mock_redis: AsyncMock
    ) -> None:
        """_process_task() should call executor.execute and publish result to tasks:results."""
        mock_executor.execute.return_value = ExecutionResult(
            success=True,
            stdout="output text",
            stderr="",
            output_path="/some/path",
        )

        data = {"task_id": "task-1", "worker_prompt": json.dumps({"prompt": "Write code"})}
        with patch("worker.consumer.WorkerGitOps"):
            await consumer._process_task("msg-id-1", data)

        mock_executor.execute.assert_called_once_with("Write code", {"task_id": "task-1"})
        mock_redis.xadd.assert_called_once()
        call_args = mock_redis.xadd.call_args
        assert call_args[0][0] == "tasks:results"
        published_data = call_args[0][1]
        assert published_data["task_id"] == "task-1"
        assert published_data["type"] == "execution"
        assert published_data["success"] == "true"

    async def test_process_task_handles_execution_failure(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, mock_redis: AsyncMock
    ) -> None:
        """_process_task() should publish failure result when executor raises."""
        mock_executor.execute.side_effect = RuntimeError("Executor crashed")

        data = {"task_id": "task-2", "worker_prompt": "simple prompt"}
        await consumer._process_task("msg-id-2", data)

        # Should still publish a result (error)
        mock_redis.xadd.assert_called_once()
        call_args = mock_redis.xadd.call_args
        published_data = call_args[0][1]
        assert published_data["success"] == "false"
        assert "Executor crashed" in published_data["error_message"]

    async def test_process_task_always_calls_xack(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, mock_redis: AsyncMock
    ) -> None:
        """_process_task() should always call XACK even on failure."""
        mock_executor.execute.side_effect = RuntimeError("fail")

        data = {"task_id": "task-3", "worker_prompt": "prompt"}
        await consumer._process_task("msg-id-3", data)

        mock_redis.xack.assert_called_once_with("tasks:queue", "workers", "msg-id-3")

    async def test_process_task_xack_on_success(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, mock_redis: AsyncMock
    ) -> None:
        """_process_task() should call XACK on success."""
        mock_executor.execute.return_value = ExecutionResult(success=True)

        data = {"task_id": "task-4", "worker_prompt": "prompt"}
        with patch("worker.consumer.WorkerGitOps"):
            await consumer._process_task("msg-id-4", data)

        mock_redis.xack.assert_called_once_with("tasks:queue", "workers", "msg-id-4")

    async def test_process_task_handles_bytes_data(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, mock_redis: AsyncMock
    ) -> None:
        """_process_task() should handle bytes values in data dict."""
        mock_executor.execute.return_value = ExecutionResult(success=True)

        data = {"task_id": b"task-bytes", "worker_prompt": b'{"prompt": "do stuff"}'}
        with patch("worker.consumer.WorkerGitOps"):
            await consumer._process_task("msg-id-5", data)

        mock_executor.execute.assert_called_once_with("do stuff", {"task_id": "task-bytes"})

    async def test_process_task_handles_plain_string_prompt(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, mock_redis: AsyncMock
    ) -> None:
        """_process_task() should handle non-JSON worker_prompt as plain string."""
        mock_executor.execute.return_value = ExecutionResult(success=True)

        data = {"task_id": "task-6", "worker_prompt": "plain text prompt"}
        with patch("worker.consumer.WorkerGitOps"):
            await consumer._process_task("msg-id-6", data)

        mock_executor.execute.assert_called_once_with("plain text prompt", {"task_id": "task-6"})

    async def test_process_task_with_repo_path_initializes_git(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, mock_redis: AsyncMock
    ) -> None:
        """_process_task() should init git repo and set workspace_dir when repo_path is provided."""
        mock_executor.execute.return_value = ExecutionResult(success=True)

        data = {
            "task_id": "task-git",
            "worker_prompt": json.dumps({"prompt": "code"}),
            "repo_path": "/home/worker/project",
            "branch_name": "phase/auth",
            "title": "Add login",
        }

        with patch("worker.consumer.WorkerGitOps") as MockGitOps:
            mock_git = AsyncMock()
            mock_git.commit_task = AsyncMock(return_value="abc123hash")
            MockGitOps.return_value = mock_git

            await consumer._process_task("msg-git", data)

        MockGitOps.assert_called_once_with("/home/worker/project")
        mock_git.ensure_repo.assert_awaited_once()
        mock_git.ensure_branch.assert_awaited_once_with("phase/auth")
        mock_executor.execute.assert_called_once_with(
            "code", {"task_id": "task-git", "workspace_dir": "/home/worker/project"}
        )
        mock_git.commit_task.assert_awaited_once_with("task-git", "Add login", "phase/auth")

        # Verify commit_hash is in the published result
        call_args = mock_redis.xadd.call_args
        published_data = call_args[0][1]
        assert published_data["commit_hash"] == "abc123hash"
        assert published_data["branch_name"] == "phase/auth"

    async def test_process_task_git_commit_failure_does_not_fail_task(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, mock_redis: AsyncMock
    ) -> None:
        """Git commit failure should not cause the task to fail."""
        mock_executor.execute.return_value = ExecutionResult(success=True)

        data = {
            "task_id": "task-gitfail",
            "worker_prompt": json.dumps({"prompt": "code"}),
            "repo_path": "/repo",
            "branch_name": "phase/test",
            "title": "Test",
        }

        with patch("worker.consumer.WorkerGitOps") as MockGitOps:
            mock_git = AsyncMock()
            mock_git.commit_task = AsyncMock(side_effect=RuntimeError("git failed"))
            MockGitOps.return_value = mock_git

            await consumer._process_task("msg-gitfail", data)

        call_args = mock_redis.xadd.call_args
        published_data = call_args[0][1]
        assert published_data["success"] == "true"
        assert published_data["commit_hash"] == ""

    async def test_process_task_no_commit_on_failure(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, mock_redis: AsyncMock
    ) -> None:
        """Should not attempt git commit when execution fails."""
        mock_executor.execute.return_value = ExecutionResult(success=False, error_message="compile error")

        data = {
            "task_id": "task-nocommit",
            "worker_prompt": json.dumps({"prompt": "code"}),
            "repo_path": "/repo",
            "branch_name": "phase/test",
            "title": "Test",
        }

        with patch("worker.consumer.WorkerGitOps") as MockGitOps:
            mock_git = AsyncMock()
            MockGitOps.return_value = mock_git

            await consumer._process_task("msg-nocommit", data)

        mock_git.commit_task.assert_not_awaited()


class TestProcessRevert:
    async def test_process_revert_calls_git_revert(
        self, consumer: TaskConsumer, mock_redis: AsyncMock
    ) -> None:
        """_process_revert() should call WorkerGitOps.revert_task."""
        data = {
            "type": "revert",
            "task_id": "task-rev",
            "repo_path": "/repo/path",
            "commit_hash": "abc123",
            "branch_name": "phase/auth",
        }

        with patch("worker.consumer.WorkerGitOps") as MockGitOps:
            mock_git = AsyncMock()
            MockGitOps.return_value = mock_git

            await consumer._process_task("msg-rev", data)

        MockGitOps.assert_called_once_with("/repo/path")
        mock_git.revert_task.assert_awaited_once_with("abc123", "phase/auth")
        mock_redis.xack.assert_called_once()

    async def test_process_revert_handles_failure_gracefully(
        self, consumer: TaskConsumer, mock_redis: AsyncMock
    ) -> None:
        """_process_revert() should not raise on git failure."""
        data = {
            "type": "revert",
            "task_id": "task-rev-fail",
            "repo_path": "/repo/path",
            "commit_hash": "abc123",
            "branch_name": "phase/auth",
        }

        with patch("worker.consumer.WorkerGitOps") as MockGitOps:
            mock_git = AsyncMock()
            mock_git.revert_task = AsyncMock(side_effect=RuntimeError("revert failed"))
            MockGitOps.return_value = mock_git

            await consumer._process_task("msg-rev-fail", data)

        # Should still XACK
        mock_redis.xack.assert_called_once()

    async def test_process_revert_skips_when_missing_fields(
        self, consumer: TaskConsumer, mock_redis: AsyncMock
    ) -> None:
        """_process_revert() should skip revert when required fields are missing."""
        data = {
            "type": "revert",
            "task_id": "task-rev-skip",
            "repo_path": "",
            "commit_hash": "",
            "branch_name": "",
        }

        with patch("worker.consumer.WorkerGitOps") as MockGitOps:
            await consumer._process_task("msg-rev-skip", data)

        MockGitOps.assert_not_called()
        mock_redis.xack.assert_called_once()


class TestProcessQA:
    async def test_process_qa_calls_executor_and_publishes_result(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, mock_redis: AsyncMock
    ) -> None:
        """_process_qa() should call executor.review and publish result to tasks:results."""
        mock_executor.review.return_value = ReviewResult(
            passed=True,
            feedback="Looks good!",
        )

        data = {"task_id": "qa-1", "qa_prompt": json.dumps({"prompt": "Review this code"})}
        await consumer._process_qa("msg-id-qa-1", data)

        mock_executor.review.assert_called_once_with("Review this code", {"task_id": "qa-1"})
        mock_redis.xadd.assert_called_once()
        call_args = mock_redis.xadd.call_args
        assert call_args[0][0] == "tasks:results"
        published_data = call_args[0][1]
        assert published_data["task_id"] == "qa-1"
        assert published_data["type"] == "qa"
        assert published_data["passed"] == "true"
        assert published_data["feedback"] == "Looks good!"

    async def test_process_qa_handles_review_failure(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, mock_redis: AsyncMock
    ) -> None:
        """_process_qa() should publish failure result when executor.review raises."""
        mock_executor.review.side_effect = RuntimeError("Review crashed")

        data = {"task_id": "qa-2", "qa_prompt": "review prompt"}
        await consumer._process_qa("msg-id-qa-2", data)

        mock_redis.xadd.assert_called_once()
        call_args = mock_redis.xadd.call_args
        published_data = call_args[0][1]
        assert published_data["passed"] == "false"
        assert "Review crashed" in published_data["error_message"]

    async def test_process_qa_always_calls_xack(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, mock_redis: AsyncMock
    ) -> None:
        """_process_qa() should always call XACK even on failure."""
        mock_executor.review.side_effect = RuntimeError("fail")

        data = {"task_id": "qa-3", "qa_prompt": "prompt"}
        await consumer._process_qa("msg-id-qa-3", data)

        mock_redis.xack.assert_called_once_with("tasks:qa", "reviewers", "msg-id-qa-3")

    async def test_process_qa_xack_on_success(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, mock_redis: AsyncMock
    ) -> None:
        """_process_qa() should call XACK on success."""
        mock_executor.review.return_value = ReviewResult(passed=False, feedback="Needs work")

        data = {"task_id": "qa-4", "qa_prompt": "prompt"}
        await consumer._process_qa("msg-id-qa-4", data)

        mock_redis.xack.assert_called_once_with("tasks:qa", "reviewers", "msg-id-qa-4")

    async def test_process_qa_handles_bytes_data(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, mock_redis: AsyncMock
    ) -> None:
        """_process_qa() should handle bytes values in data dict."""
        mock_executor.review.return_value = ReviewResult(passed=True, feedback="OK")

        data = {"task_id": b"qa-bytes", "qa_prompt": b'{"prompt": "review stuff"}'}
        await consumer._process_qa("msg-id-qa-5", data)

        mock_executor.review.assert_called_once_with("review stuff", {"task_id": "qa-bytes"})

    async def test_process_qa_with_repo_path_sets_workspace_dir(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, mock_redis: AsyncMock
    ) -> None:
        """_process_qa() should pass workspace_dir in context when repo_path is provided."""
        mock_executor.review.return_value = ReviewResult(passed=True, feedback="OK")

        data = {
            "task_id": "qa-repo",
            "qa_prompt": json.dumps({"prompt": "review"}),
            "repo_path": "/home/worker/project",
        }
        await consumer._process_qa("msg-qa-repo", data)

        mock_executor.review.assert_called_once_with(
            "review", {"task_id": "qa-repo", "workspace_dir": "/home/worker/project"}
        )
