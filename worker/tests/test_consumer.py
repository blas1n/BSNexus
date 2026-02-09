import json
from unittest.mock import AsyncMock

import pytest

from worker.src.agent import WorkerAgent
from worker.src.config import WorkerConfig
from worker.src.consumer import TaskConsumer
from worker.src.executors.base import BaseExecutor, ExecutionResult, ReviewResult


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
        await consumer._process_task("msg-id-4", data)

        mock_redis.xack.assert_called_once_with("tasks:queue", "workers", "msg-id-4")

    async def test_process_task_handles_bytes_data(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, mock_redis: AsyncMock
    ) -> None:
        """_process_task() should handle bytes values in data dict."""
        mock_executor.execute.return_value = ExecutionResult(success=True)

        data = {"task_id": b"task-bytes", "worker_prompt": b'{"prompt": "do stuff"}'}
        await consumer._process_task("msg-id-5", data)

        mock_executor.execute.assert_called_once_with("do stuff", {"task_id": "task-bytes"})

    async def test_process_task_handles_plain_string_prompt(
        self, consumer: TaskConsumer, mock_executor: AsyncMock, mock_redis: AsyncMock
    ) -> None:
        """_process_task() should handle non-JSON worker_prompt as plain string."""
        mock_executor.execute.return_value = ExecutionResult(success=True)

        data = {"task_id": "task-6", "worker_prompt": "plain text prompt"}
        await consumer._process_task("msg-id-6", data)

        mock_executor.execute.assert_called_once_with("plain text prompt", {"task_id": "task-6"})


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
