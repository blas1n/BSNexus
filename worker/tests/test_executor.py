import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from worker.src.executor import create_executor
from worker.src.executors.claude_code import ClaudeCodeExecutor


class TestExecutorFactory:
    def test_create_executor_claude_code(self) -> None:
        """create_executor('claude-code') should return a ClaudeCodeExecutor instance."""
        executor = create_executor("claude-code")
        assert isinstance(executor, ClaudeCodeExecutor)

    def test_create_executor_unknown_raises(self) -> None:
        """create_executor('unknown') should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown executor: unknown"):
            create_executor("unknown")

    def test_create_executor_passes_kwargs(self) -> None:
        """create_executor should pass kwargs to the executor constructor."""
        executor = create_executor("claude-code", workspace_dir="/custom/dir")
        assert isinstance(executor, ClaudeCodeExecutor)
        assert executor.workspace_dir == "/custom/dir"


class TestClaudeCodeExecutorExecute:
    async def test_execute_success(self) -> None:
        """execute() should return success when subprocess exits with 0."""
        executor = ClaudeCodeExecutor(workspace_dir="/test")

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"Hello output", b""))

        with patch("worker.src.executors.claude_code.asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute("Write code", {"task_id": "t1"})

        assert result.success is True
        assert result.stdout == "Hello output"
        assert result.stderr == ""
        assert result.error_message is None

    async def test_execute_failure(self) -> None:
        """execute() should return failure when subprocess exits with non-zero."""
        executor = ClaudeCodeExecutor(workspace_dir="/test")

        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"Error occurred"))

        with patch("worker.src.executors.claude_code.asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute("Write code", {"task_id": "t2"})

        assert result.success is False
        assert result.error_message == "Error occurred"

    async def test_execute_timeout(self) -> None:
        """execute() should return timeout error when process exceeds time limit."""
        executor = ClaudeCodeExecutor(workspace_dir="/test")

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError)

        with patch("worker.src.executors.claude_code.asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute("Write code", {"task_id": "t3"})

        assert result.success is False
        assert "timed out" in (result.error_message or "").lower()

    async def test_execute_calls_claude_cli(self) -> None:
        """execute() should call 'claude' CLI with correct arguments."""
        executor = ClaudeCodeExecutor(workspace_dir="/my/workspace")

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"ok", b""))

        with patch(
            "worker.src.executors.claude_code.asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_exec:
            await executor.execute("Do something", {"task_id": "t4"})

        mock_exec.assert_called_once()
        call_args = mock_exec.call_args[0]
        assert call_args[0] == "claude"
        assert "--print" in call_args
        assert "--dangerously-skip-permissions" in call_args
        assert "-p" in call_args
        assert "Do something" in call_args
        assert mock_exec.call_args[1]["cwd"] == "/my/workspace"


class TestClaudeCodeExecutorReview:
    async def test_review_pass(self) -> None:
        """review() should return passed=True when output starts with 'PASS'."""
        executor = ClaudeCodeExecutor(workspace_dir="/test")

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"PASS - Code looks clean and well-structured.", b""))

        with patch("worker.src.executors.claude_code.asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.review("Review this", {"task_id": "r1"})

        assert result.passed is True
        assert "PASS" in result.feedback

    async def test_review_fail(self) -> None:
        """review() should return passed=False when output starts with 'FAIL'."""
        executor = ClaudeCodeExecutor(workspace_dir="/test")

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"FAIL - Missing error handling.", b""))

        with patch("worker.src.executors.claude_code.asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.review("Review this", {"task_id": "r2"})

        assert result.passed is False
        assert "FAIL" in result.feedback

    async def test_review_execution_error(self) -> None:
        """review() should return passed=False with error_message on execution failure."""
        executor = ClaudeCodeExecutor(workspace_dir="/test")

        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"CLI error"))

        with patch("worker.src.executors.claude_code.asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.review("Review this", {"task_id": "r3"})

        assert result.passed is False
        assert result.error_message is not None
