import asyncio
import tempfile
from pathlib import Path

from worker.log import log

from .base import BaseExecutor, ExecutionResult, ReviewResult


class ClaudeCodeExecutor(BaseExecutor):
    """Claude Code CLI executor"""

    def __init__(self, workspace_dir: str = "/workspace") -> None:
        self.workspace_dir = workspace_dir

    async def execute(self, prompt: str, context: dict) -> ExecutionResult:
        """Execute coding task via Claude Code CLI"""
        task_id = context.get("task_id", "unknown")
        workspace = context.get("workspace_dir", self.workspace_dir)

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".md",
            prefix=f"task-{task_id}-",
            delete=False,
        ) as f:
            f.write(prompt)
            prompt_file = f.name

        try:
            log.info("    claude-cli: starting  task_id=%s cwd=%s", task_id, workspace)
            process = await asyncio.create_subprocess_exec(
                "claude",
                "--print",
                "--dangerously-skip-permissions",
                "-p",
                prompt,
                cwd=workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            log.info("    claude-cli: pid=%d", process.pid)

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=3600,
            )

            rc = process.returncode
            log.info("    claude-cli: finished  rc=%d stdout=%d bytes stderr=%d bytes",
                      rc, len(stdout), len(stderr))

            return ExecutionResult(
                success=rc == 0,
                stdout=stdout.decode(),
                stderr=stderr.decode(),
                error_message=stderr.decode() if rc != 0 else None,
            )

        except asyncio.TimeoutError:
            log.error("    claude-cli: TIMEOUT after 1 hour  task_id=%s", task_id)
            return ExecutionResult(
                success=False,
                error_message="Execution timed out after 1 hour",
            )
        finally:
            Path(prompt_file).unlink(missing_ok=True)

    async def review(self, prompt: str, context: dict) -> ReviewResult:
        """Execute code review via Claude Code CLI"""
        task_id = context.get("task_id", "unknown")
        log.info("    claude-cli: review starting  task_id=%s", task_id)

        review_prompt = f"""Please review the following code changes.

{prompt}

Response format:
- Start with PASS or FAIL
- Explain the reason
"""
        result = await self.execute(review_prompt, context)

        if not result.success:
            log.warning("    claude-cli: review execution failed  task_id=%s", task_id)
            return ReviewResult(passed=False, error_message=result.error_message)

        output = result.stdout.strip()
        passed = output.upper().startswith("PASS")
        log.info("    claude-cli: review result=%s  task_id=%s", "PASS" if passed else "FAIL", task_id)

        return ReviewResult(passed=passed, feedback=output)
