import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from worker.executor import create_executor
from worker.executors.claude_code import ClaudeCodeExecutor


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

        with patch("worker.executors.claude_code.asyncio.create_subprocess_exec", return_value=mock_process):
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

        with patch("worker.executors.claude_code.asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute("Write code", {"task_id": "t2"})

        assert result.success is False
        assert result.error_message == "Error occurred"

    async def test_execute_timeout(self) -> None:
        """execute() should return timeout error when process exceeds time limit."""
        executor = ClaudeCodeExecutor(workspace_dir="/test")

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError)

        with patch("worker.executors.claude_code.asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute("Write code", {"task_id": "t3"})

        assert result.success is False
        assert "timed out" in (result.error_message or "").lower()

    async def test_execute_calls_claude_cli(self) -> None:
        """execute() should call 'claude' CLI with correct arguments via stdin."""
        executor = ClaudeCodeExecutor(workspace_dir="/my/workspace")
        executor._claude_cmd = "claude"  # override resolved path for test

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"ok", b""))

        with patch(
            "worker.executors.claude_code.asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_exec:
            await executor.execute("Do something", {"task_id": "t4"})

        mock_exec.assert_called_once()
        call_args = mock_exec.call_args[0]
        assert call_args[0] == "claude"
        assert "--print" in call_args
        assert "--dangerously-skip-permissions" in call_args
        assert mock_exec.call_args[1]["cwd"] == "/my/workspace"
        assert mock_exec.call_args[1]["stdin"] == asyncio.subprocess.PIPE
        mock_process.communicate.assert_awaited_once_with(input=b"Do something")

    async def test_execute_workspace_dir_override_from_context(self) -> None:
        """execute() should use workspace_dir from context if provided."""
        executor = ClaudeCodeExecutor(workspace_dir="/default/workspace")

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"ok", b""))

        with patch(
            "worker.executors.claude_code.asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_exec:
            await executor.execute("Do something", {"task_id": "t5", "workspace_dir": "/override/path"})

        assert mock_exec.call_args[1]["cwd"] == "/override/path"

    async def test_execute_uses_default_when_no_context_override(self) -> None:
        """execute() should use self.workspace_dir when context has no override."""
        executor = ClaudeCodeExecutor(workspace_dir="/default/workspace")

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"ok", b""))

        with patch(
            "worker.executors.claude_code.asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_exec:
            await executor.execute("Do something", {"task_id": "t6"})

        assert mock_exec.call_args[1]["cwd"] == "/default/workspace"


class TestClaudeCodeExecutorReview:
    async def test_review_pass(self) -> None:
        """review() should return passed=True when output starts with 'PASS'."""
        executor = ClaudeCodeExecutor(workspace_dir="/test")

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"PASS - Code looks clean and well-structured.", b""))

        with patch("worker.executors.claude_code.asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.review("Review this", {"task_id": "r1"})

        assert result.passed is True
        assert "PASS" in result.feedback

    async def test_review_fail(self) -> None:
        """review() should return passed=False when output starts with 'FAIL'."""
        executor = ClaudeCodeExecutor(workspace_dir="/test")

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"FAIL - Missing error handling.", b""))

        with patch("worker.executors.claude_code.asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.review("Review this", {"task_id": "r2"})

        assert result.passed is False
        assert "FAIL" in result.feedback

    async def test_review_execution_error(self) -> None:
        """review() should return passed=False with error_message on execution failure."""
        executor = ClaudeCodeExecutor(workspace_dir="/test")

        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"CLI error"))

        with patch("worker.executors.claude_code.asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.review("Review this", {"task_id": "r3"})

        assert result.passed is False
        assert result.error_message is not None


class TestParseRateLimitWait:
    def test_detects_hit_your_limit(self) -> None:
        assert ClaudeCodeExecutor._parse_rate_limit_wait("You've hit your limit") == ClaudeCodeExecutor._RATE_LIMIT_WAIT_SECONDS

    def test_detects_rate_limit(self) -> None:
        assert ClaudeCodeExecutor._parse_rate_limit_wait("Rate limit exceeded") == ClaudeCodeExecutor._RATE_LIMIT_WAIT_SECONDS

    def test_case_insensitive(self) -> None:
        assert ClaudeCodeExecutor._parse_rate_limit_wait("RATE LIMIT reached") == ClaudeCodeExecutor._RATE_LIMIT_WAIT_SECONDS

    def test_no_rate_limit(self) -> None:
        assert ClaudeCodeExecutor._parse_rate_limit_wait("Normal output") is None

    def test_empty_string(self) -> None:
        assert ClaudeCodeExecutor._parse_rate_limit_wait("") is None


class TestParseReviewVerdict:
    def test_verdict_pass(self) -> None:
        assert ClaudeCodeExecutor._parse_review_verdict("Review complete\nVERDICT: PASS") is True

    def test_verdict_fail(self) -> None:
        assert ClaudeCodeExecutor._parse_review_verdict("Issues found\nVERDICT: FAIL - missing tests") is False

    def test_result_pass(self) -> None:
        assert ClaudeCodeExecutor._parse_review_verdict("RESULT: PASS") is True

    def test_result_fail(self) -> None:
        assert ClaudeCodeExecutor._parse_review_verdict("RESULT: FAIL") is False

    def test_standalone_pass(self) -> None:
        assert ClaudeCodeExecutor._parse_review_verdict("PASS - looks good") is True

    def test_standalone_fail(self) -> None:
        assert ClaudeCodeExecutor._parse_review_verdict("FAIL - broken") is False

    def test_no_verdict_defaults_false(self) -> None:
        assert ClaudeCodeExecutor._parse_review_verdict("Some review text without verdict") is False

    def test_markdown_formatting_stripped(self) -> None:
        assert ClaudeCodeExecutor._parse_review_verdict("**VERDICT: PASS**") is True

    def test_bottom_up_search(self) -> None:
        """Should find the last verdict, not the first."""
        output = "VERDICT: FAIL\nAfter fixing:\nVERDICT: PASS"
        assert ClaudeCodeExecutor._parse_review_verdict(output) is True

    def test_no_false_positive_on_passing(self) -> None:
        """Should not match 'PASSING' or 'FAILED_REASON' as a verdict."""
        assert ClaudeCodeExecutor._parse_review_verdict("PASSING all tests currently") is False

    def test_no_false_positive_on_failed(self) -> None:
        assert ClaudeCodeExecutor._parse_review_verdict("FAILED_REASON: timeout") is False
