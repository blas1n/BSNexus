import asyncio
import re
import shutil
import sys

from worker.log import log
from worker.prompts.loader import get_prompt

from .base import BaseExecutor, ExecutionResult, ReviewResult


class ClaudeCodeExecutor(BaseExecutor):
    """Claude Code CLI executor"""

    _RATE_LIMIT_MAX_RETRIES: int = 5
    _RATE_LIMIT_WAIT_SECONDS: int = 300   # 5 minutes
    _EXECUTION_TIMEOUT_SECONDS: int = 3600  # 1 hour

    def __init__(self, workspace_dir: str = "/workspace") -> None:
        self.workspace_dir = workspace_dir
        self._claude_cmd = self._resolve_claude_cmd()

    @staticmethod
    def _resolve_claude_cmd() -> str:
        """Resolve the claude CLI command path.

        On Windows, npm global installs create .cmd shims that
        asyncio.create_subprocess_exec cannot find without a shell.
        Use shutil.which to resolve the actual path.
        """
        resolved = shutil.which("claude")
        if resolved:
            return resolved
        # Windows: try claude.cmd explicitly
        if sys.platform == "win32":
            resolved = shutil.which("claude.cmd")
            if resolved:
                return resolved
        return "claude"  # fallback, let OS try

    @staticmethod
    def _parse_rate_limit_wait(output: str) -> int | None:
        """Detect rate limit from CLI output. Returns seconds to wait, or None."""
        lower = output.lower()
        if "hit your limit" in lower or "rate limit" in lower:
            return ClaudeCodeExecutor._RATE_LIMIT_WAIT_SECONDS
        return None

    async def execute(self, prompt: str, context: dict) -> ExecutionResult:
        """Execute coding task via Claude Code CLI, with rate limit retry."""
        task_id = context.get("task_id", "unknown")
        workspace = context.get("workspace_dir", self.workspace_dir)
        return await self._execute_with_rate_limit_retry(prompt, task_id, workspace)

    async def _execute_with_rate_limit_retry(
        self, prompt: str, task_id: str, workspace: str,
    ) -> ExecutionResult:
        """Run CLI, retrying on rate limit until reset."""
        max_retries = self._RATE_LIMIT_MAX_RETRIES
        result: ExecutionResult | None = None
        for attempt in range(max_retries + 1):
            result = await self._run_cli(prompt, task_id, workspace)
            if result.success:
                return result
            # Check for rate limit
            output = (result.stdout or "") + (result.stderr or "")
            wait_seconds = self._parse_rate_limit_wait(output)
            if wait_seconds is None:
                return result  # not a rate limit error
            if attempt >= max_retries:
                log.error("    claude-cli: rate limit retry exhausted after %d attempts  task_id=%s", max_retries, task_id)
                return result
            log.warning(
                "    claude-cli: rate limited, waiting %d seconds (attempt %d/%d)  task_id=%s",
                wait_seconds, attempt + 1, max_retries, task_id,
            )
            await asyncio.sleep(wait_seconds)
        assert result is not None, "max_retries must be >= 0"
        return result

    async def _run_cli(self, prompt: str, task_id: str, workspace: str) -> ExecutionResult:
        """Single CLI invocation."""
        try:
            log.info("    claude-cli: starting  task_id=%s cwd=%s cmd=%s", task_id, workspace, self._claude_cmd)
            log.info("    claude-cli: prompt length=%d chars", len(prompt))
            prompt_bytes = prompt.encode("utf-8")
            process = await asyncio.create_subprocess_exec(
                self._claude_cmd,
                "--print",
                "--dangerously-skip-permissions",
                cwd=workspace,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            log.info("    claude-cli: pid=%d", process.pid)

            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=prompt_bytes),
                timeout=self._EXECUTION_TIMEOUT_SECONDS,
            )

            rc = process.returncode
            out = stdout.decode("utf-8", errors="replace")
            err = stderr.decode("utf-8", errors="replace")
            log.info("    claude-cli: finished  rc=%d stdout=%d bytes stderr=%d bytes",
                      rc, len(stdout), len(stderr))
            if out:
                log.debug("    claude-cli: stdout >>>>\n%s\n    <<<< end stdout", out)
            if err:
                log.debug("    claude-cli: stderr >>>>\n%s\n    <<<< end stderr", err)

            return ExecutionResult(
                success=rc == 0,
                stdout=out,
                stderr=err,
                error_message=err if rc != 0 else None,
                error_category="" if rc == 0 else "tool",
            )

        except asyncio.TimeoutError:
            log.error(
                "    claude-cli: TIMEOUT after %ds  task_id=%s", self._EXECUTION_TIMEOUT_SECONDS, task_id,
            )
            return ExecutionResult(
                success=False,
                error_message=f"Execution timed out after {self._EXECUTION_TIMEOUT_SECONDS}s",
                error_category="environment",
            )
        except (FileNotFoundError, PermissionError, OSError, UnicodeEncodeError) as e:
            log.error("    claude-cli: environment error  task_id=%s error=%s", task_id, e)
            return ExecutionResult(
                success=False,
                error_message=str(e),
                error_category="environment",
            )

    async def review(self, prompt: str, context: dict) -> ReviewResult:
        """Execute code review via Claude Code CLI"""
        task_id = context.get("task_id", "unknown")
        log.info("    claude-cli: review starting  task_id=%s", task_id)

        review_prompt = get_prompt("review", "code_review").format(task_prompt=prompt)
        result = await self.execute(review_prompt, context)

        if not result.success:
            log.warning("    claude-cli: review execution failed  task_id=%s", task_id)
            return ReviewResult(passed=False, error_message=result.error_message, error_category=result.error_category)

        output = result.stdout.strip()
        passed = self._parse_review_verdict(output)
        log.info("    claude-cli: review result=%s  task_id=%s", "PASS" if passed else "FAIL", task_id)

        return ReviewResult(passed=passed, feedback=output)

    @staticmethod
    def _parse_review_verdict(output: str) -> bool:
        """Parse PASS/FAIL verdict from review output.

        Searches the output from bottom to top for a verdict line.
        Falls back to scanning for common verdict patterns.
        """
        lines = output.strip().splitlines()

        # Strategy 1: Look for "VERDICT: PASS/FAIL" or "RESULT: PASS/FAIL" from bottom up
        for line in reversed(lines):
            # Strip markdown formatting (**, *, `)
            cleaned = re.sub(r"[*`#]", "", line).strip().upper()
            if re.match(r"^(VERDICT|RESULT)\s*:\s*PASS", cleaned):
                return True
            if re.match(r"^(VERDICT|RESULT)\s*:\s*FAIL", cleaned):
                return False

        # Strategy 2: Look for standalone PASS or FAIL keywords (bottom up)
        # Use word boundary to avoid false positives like "PASSING" or "FAILED_REASON"
        for line in reversed(lines):
            cleaned = re.sub(r"[*`#]", "", line).strip().upper()
            if re.match(r"^(PASS|FAIL)\b", cleaned):
                return True if cleaned.startswith("PASS") else False

        # Default: if no verdict signal found, fail safe
        return False
