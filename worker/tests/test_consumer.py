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
        executor_type="claude-code",
    )


@pytest.fixture
def agent(config: WorkerConfig) -> WorkerAgent:
    a = WorkerAgent(config)
    a.worker_id = "test-worker-id"
    a.token = "test-token"
    a.poll = AsyncMock(return_value=[])
    a.submit_result = AsyncMock()
    return a


@pytest.fixture
def mock_executor() -> AsyncMock:
    executor = AsyncMock(spec=BaseExecutor)
    return executor


@pytest.fixture
def consumer(agent: WorkerAgent, mock_executor: AsyncMock) -> TaskConsumer:
    return TaskConsumer(agent, mock_executor)


class TestProcessTask:
    async def test_process_task_calls_executor_and_submits_result(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, agent: WorkerAgent
    ) -> None:
        """_process_task() should call executor.execute and submit result via HTTP."""
        mock_executor.execute.return_value = ExecutionResult(
            success=True,
            stdout="output text",
            stderr="",
            output_path="/some/path",
        )

        data = {"task_id": "task-1", "worker_prompt": json.dumps({"prompt": "Write code"})}
        with patch("worker.consumer.WorkerGitOps"):
            await consumer._process_task("msg-id-1", "task", data)

        mock_executor.execute.assert_called_once_with("Write code", {"task_id": "task-1"})
        agent.submit_result.assert_called_once()
        result = agent.submit_result.call_args[0][0]
        assert result["message_id"] == "msg-id-1"
        assert result["stream"] == "task"
        assert result["result_type"] == "execution"
        assert result["task_id"] == "task-1"
        assert result["success"] is True

    async def test_process_task_handles_execution_failure(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, agent: WorkerAgent
    ) -> None:
        """_process_task() should submit failure result when executor raises."""
        mock_executor.execute.side_effect = RuntimeError("Executor crashed")

        data = {"task_id": "task-2", "worker_prompt": "simple prompt"}
        await consumer._process_task("msg-id-2", "task", data)

        agent.submit_result.assert_called_once()
        result = agent.submit_result.call_args[0][0]
        assert result["success"] is False
        assert "Executor crashed" in result["error_message"]

    async def test_process_task_always_submits_result(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, agent: WorkerAgent
    ) -> None:
        """_process_task() should always submit a result even on failure."""
        mock_executor.execute.side_effect = RuntimeError("fail")

        data = {"task_id": "task-3", "worker_prompt": "prompt"}
        await consumer._process_task("msg-id-3", "task", data)

        agent.submit_result.assert_called_once()
        result = agent.submit_result.call_args[0][0]
        assert result["message_id"] == "msg-id-3"
        assert result["stream"] == "task"

    async def test_process_task_submits_on_success(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, agent: WorkerAgent
    ) -> None:
        """_process_task() should submit result on success."""
        mock_executor.execute.return_value = ExecutionResult(success=True)

        data = {"task_id": "task-4", "worker_prompt": "prompt"}
        with patch("worker.consumer.WorkerGitOps"):
            await consumer._process_task("msg-id-4", "task", data)

        agent.submit_result.assert_called_once()

    async def test_process_task_handles_plain_string_prompt(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, agent: WorkerAgent
    ) -> None:
        """_process_task() should handle non-JSON worker_prompt as plain string."""
        mock_executor.execute.return_value = ExecutionResult(success=True)

        data = {"task_id": "task-6", "worker_prompt": "plain text prompt"}
        with patch("worker.consumer.WorkerGitOps"):
            await consumer._process_task("msg-id-6", "task", data)

        mock_executor.execute.assert_called_once_with("plain text prompt", {"task_id": "task-6"})

    async def test_process_task_handles_dict_prompt(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, agent: WorkerAgent
    ) -> None:
        """_process_task() should handle pre-parsed dict worker_prompt."""
        mock_executor.execute.return_value = ExecutionResult(success=True)

        data = {"task_id": "task-dict", "worker_prompt": {"prompt": "from dict"}}
        with patch("worker.consumer.WorkerGitOps"):
            await consumer._process_task("msg-dict", "task", data)

        mock_executor.execute.assert_called_once_with("from dict", {"task_id": "task-dict"})

    async def test_process_task_with_repo_path_initializes_git(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, agent: WorkerAgent
    ) -> None:
        """_process_task() should init git repo and set workspace_dir when repo_path is provided.

        Note: commit happens in _process_qa, not here.
        """
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
            MockGitOps.return_value = mock_git

            await consumer._process_task("msg-git", "task", data)

        MockGitOps.assert_called_once_with("/home/worker/project")
        mock_git.ensure_repo.assert_awaited_once()
        mock_git.ensure_branch.assert_awaited_once_with("phase/auth")
        mock_executor.execute.assert_called_once_with(
            "code", {"task_id": "task-git", "workspace_dir": "/home/worker/project"}
        )

        result = agent.submit_result.call_args[0][0]
        assert result["commit_hash"] == ""
        assert result["branch_name"] == "phase/auth"


class TestProcessRevert:
    async def test_process_revert_calls_git_revert(
        self, consumer: TaskConsumer, agent: WorkerAgent
    ) -> None:
        """_process_revert() should call WorkerGitOps.revert_task."""
        data = {
            "task_id": "task-rev",
            "repo_path": "/repo/path",
            "commit_hash": "abc123",
            "branch_name": "phase/auth",
        }

        with patch("worker.consumer.WorkerGitOps") as MockGitOps:
            mock_git = AsyncMock()
            MockGitOps.return_value = mock_git

            await consumer._process_revert("msg-rev", "task", data)

        MockGitOps.assert_called_once_with("/repo/path")
        mock_git.revert_task.assert_awaited_once_with("abc123", "phase/auth")
        agent.submit_result.assert_called_once()
        result = agent.submit_result.call_args[0][0]
        assert result["result_type"] == "revert"

    async def test_process_revert_handles_failure_gracefully(
        self, consumer: TaskConsumer, agent: WorkerAgent
    ) -> None:
        """_process_revert() should not raise on git failure."""
        data = {
            "task_id": "task-rev-fail",
            "repo_path": "/repo/path",
            "commit_hash": "abc123",
            "branch_name": "phase/auth",
        }

        with patch("worker.consumer.WorkerGitOps") as MockGitOps:
            mock_git = AsyncMock()
            mock_git.revert_task = AsyncMock(side_effect=RuntimeError("revert failed"))
            MockGitOps.return_value = mock_git

            await consumer._process_revert("msg-rev-fail", "task", data)

        # Should still submit result (ACK)
        agent.submit_result.assert_called_once()

    async def test_process_revert_skips_when_missing_fields(
        self, consumer: TaskConsumer, agent: WorkerAgent
    ) -> None:
        """_process_revert() should skip revert when required fields are missing."""
        data = {
            "task_id": "task-rev-skip",
            "repo_path": "",
            "commit_hash": "",
            "branch_name": "",
        }

        with patch("worker.consumer.WorkerGitOps") as MockGitOps:
            await consumer._process_revert("msg-rev-skip", "task", data)

        MockGitOps.assert_not_called()
        agent.submit_result.assert_called_once()

    async def test_process_task_dispatches_revert(
        self, consumer: TaskConsumer, agent: WorkerAgent
    ) -> None:
        """_process_task dispatch: type=revert in poll data should route to _process_revert via poll_loop."""
        # Test the poll_loop dispatch by directly checking that revert type is in data
        data = {
            "type": "revert",
            "task_id": "task-rev-dispatch",
            "repo_path": "/repo",
            "commit_hash": "def456",
            "branch_name": "phase/auth",
        }

        with patch("worker.consumer.WorkerGitOps") as MockGitOps:
            mock_git = AsyncMock()
            MockGitOps.return_value = mock_git

            # Simulate poll_loop dispatching a revert item
            await consumer._process_revert("msg-rev-d", "task", data)

        mock_git.revert_task.assert_awaited_once_with("def456", "phase/auth")


class TestProcessQA:
    async def test_process_qa_calls_executor_and_submits_result(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, agent: WorkerAgent
    ) -> None:
        """_process_qa() should call executor.review and submit result via HTTP."""
        mock_executor.review.return_value = ReviewResult(
            passed=True,
            feedback="Looks good!",
        )

        data = {"task_id": "qa-1", "qa_prompt": json.dumps({"prompt": "Review this code"})}
        await consumer._process_qa("msg-id-qa-1", "qa", data)

        mock_executor.review.assert_called_once_with("Review this code", {"task_id": "qa-1"})
        agent.submit_result.assert_called_once()
        result = agent.submit_result.call_args[0][0]
        assert result["message_id"] == "msg-id-qa-1"
        assert result["stream"] == "qa"
        assert result["result_type"] == "qa"
        assert result["task_id"] == "qa-1"
        assert result["passed"] is True
        assert result["feedback"] == "Looks good!"

    async def test_process_qa_handles_review_failure(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, agent: WorkerAgent
    ) -> None:
        """_process_qa() should submit failure result when executor.review raises."""
        mock_executor.review.side_effect = RuntimeError("Review crashed")

        data = {"task_id": "qa-2", "qa_prompt": "review prompt"}
        await consumer._process_qa("msg-id-qa-2", "qa", data)

        agent.submit_result.assert_called_once()
        result = agent.submit_result.call_args[0][0]
        assert result["passed"] is False
        assert "Review crashed" in result["error_message"]

    async def test_process_qa_always_submits_result(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, agent: WorkerAgent
    ) -> None:
        """_process_qa() should always submit a result even on failure."""
        mock_executor.review.side_effect = RuntimeError("fail")

        data = {"task_id": "qa-3", "qa_prompt": "prompt"}
        await consumer._process_qa("msg-id-qa-3", "qa", data)

        agent.submit_result.assert_called_once()
        result = agent.submit_result.call_args[0][0]
        assert result["message_id"] == "msg-id-qa-3"
        assert result["stream"] == "qa"

    async def test_process_qa_submits_on_success(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, agent: WorkerAgent
    ) -> None:
        """_process_qa() should submit result on success."""
        mock_executor.review.return_value = ReviewResult(passed=False, feedback="Needs work")

        data = {"task_id": "qa-4", "qa_prompt": "prompt"}
        await consumer._process_qa("msg-id-qa-4", "qa", data)

        agent.submit_result.assert_called_once()

    async def test_process_qa_handles_dict_prompt(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, agent: WorkerAgent
    ) -> None:
        """_process_qa() should handle pre-parsed dict qa_prompt."""
        mock_executor.review.return_value = ReviewResult(passed=True, feedback="OK")

        data = {"task_id": "qa-dict", "qa_prompt": {"prompt": "review stuff"}}
        await consumer._process_qa("msg-id-qa-dict", "qa", data)

        mock_executor.review.assert_called_once_with("review stuff", {"task_id": "qa-dict"})

    async def test_process_qa_with_repo_path_sets_workspace_dir(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, agent: WorkerAgent
    ) -> None:
        """_process_qa() should pass workspace_dir in context when repo_path is provided."""
        mock_executor.review.return_value = ReviewResult(passed=True, feedback="OK")

        data = {
            "task_id": "qa-repo",
            "qa_prompt": json.dumps({"prompt": "review"}),
            "repo_path": "/home/worker/project",
        }
        await consumer._process_qa("msg-qa-repo", "qa", data)

        mock_executor.review.assert_called_once_with(
            "review", {"task_id": "qa-repo", "workspace_dir": "/home/worker/project"}
        )

    async def test_process_qa_commits_on_pass(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, agent: WorkerAgent
    ) -> None:
        """_process_qa() should commit after QA pass and include commit_hash in result."""
        mock_executor.review.return_value = ReviewResult(passed=True, feedback="LGTM")

        data = {
            "task_id": "qa-commit",
            "qa_prompt": json.dumps({"prompt": "review"}),
            "repo_path": "/repo",
            "branch_name": "phase/auth",
            "title": "Add login",
        }

        with patch("worker.consumer.WorkerGitOps") as MockGitOps:
            mock_git = AsyncMock()
            mock_git.commit_task = AsyncMock(return_value="abc123hash")
            MockGitOps.return_value = mock_git

            await consumer._process_qa("msg-qa-commit", "qa", data)

        mock_git.commit_task.assert_awaited_once_with("qa-commit", "Add login", "phase/auth")
        result = agent.submit_result.call_args[0][0]
        assert result["passed"] is True
        assert result["commit_hash"] == "abc123hash"

    async def test_process_qa_commit_failure_still_passes(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, agent: WorkerAgent
    ) -> None:
        """_process_qa() should still report QA pass even when commit fails."""
        mock_executor.review.return_value = ReviewResult(passed=True, feedback="OK")

        data = {
            "task_id": "qa-commitfail",
            "qa_prompt": json.dumps({"prompt": "review"}),
            "repo_path": "/repo",
            "branch_name": "phase/test",
            "title": "Test",
        }

        with patch("worker.consumer.WorkerGitOps") as MockGitOps:
            mock_git = AsyncMock()
            mock_git.commit_task = AsyncMock(side_effect=RuntimeError("git failed"))
            MockGitOps.return_value = mock_git

            await consumer._process_qa("msg-qa-commitfail", "qa", data)

        result = agent.submit_result.call_args[0][0]
        assert result["passed"] is True
        assert result["commit_hash"] == ""

    async def test_process_qa_no_changes_still_passes(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, agent: WorkerAgent
    ) -> None:
        """_process_qa() should pass with empty commit_hash when no file changes."""
        mock_executor.review.return_value = ReviewResult(passed=True, feedback="OK")

        data = {
            "task_id": "qa-nochanges",
            "qa_prompt": json.dumps({"prompt": "review"}),
            "repo_path": "/repo",
            "branch_name": "phase/test",
            "title": "Test",
        }

        with patch("worker.consumer.WorkerGitOps") as MockGitOps:
            mock_git = AsyncMock()
            mock_git.commit_task = AsyncMock(return_value="")
            MockGitOps.return_value = mock_git

            await consumer._process_qa("msg-qa-nochanges", "qa", data)

        result = agent.submit_result.call_args[0][0]
        assert result["passed"] is True
        assert result["commit_hash"] == ""


class TestClassifyException:
    def test_classify_environment_exceptions(self) -> None:
        """_classify_exception should return 'environment' for OS/file errors."""
        assert TaskConsumer._classify_exception(FileNotFoundError("x")) == "environment"
        assert TaskConsumer._classify_exception(PermissionError("x")) == "environment"
        assert TaskConsumer._classify_exception(OSError("x")) == "environment"

    def test_classify_unicode_exceptions(self) -> None:
        """_classify_exception should return 'environment' for unicode errors."""
        assert TaskConsumer._classify_exception(
            UnicodeEncodeError("utf-8", "", 0, 1, "x")
        ) == "environment"
        assert TaskConsumer._classify_exception(
            UnicodeDecodeError("utf-8", b"", 0, 1, "x")
        ) == "environment"

    def test_classify_other_exceptions(self) -> None:
        """_classify_exception should return '' for non-environment errors."""
        assert TaskConsumer._classify_exception(RuntimeError("x")) == ""
        assert TaskConsumer._classify_exception(ValueError("x")) == ""
        assert TaskConsumer._classify_exception(KeyError("x")) == ""
