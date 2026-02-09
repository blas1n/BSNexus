import asyncio
import tempfile
from pathlib import Path

from .base import BaseExecutor, ExecutionResult, ReviewResult


class ClaudeCodeExecutor(BaseExecutor):
    """Claude Code CLI executor"""

    def __init__(self, workspace_dir: str = "/workspace") -> None:
        self.workspace_dir = workspace_dir

    async def execute(self, prompt: str, context: dict) -> ExecutionResult:
        """Execute coding task via Claude Code CLI"""
        task_id = context.get("task_id", "unknown")

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".md",
            prefix=f"task-{task_id}-",
            delete=False,
        ) as f:
            f.write(prompt)
            prompt_file = f.name

        try:
            process = await asyncio.create_subprocess_exec(
                "claude",
                "--print",
                "--dangerously-skip-permissions",
                "-p",
                prompt,
                cwd=self.workspace_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=3600,
            )

            return ExecutionResult(
                success=process.returncode == 0,
                stdout=stdout.decode(),
                stderr=stderr.decode(),
                error_message=stderr.decode() if process.returncode != 0 else None,
            )

        except asyncio.TimeoutError:
            return ExecutionResult(
                success=False,
                error_message="Execution timed out after 1 hour",
            )
        finally:
            Path(prompt_file).unlink(missing_ok=True)

    async def review(self, prompt: str, context: dict) -> ReviewResult:
        """Execute code review via Claude Code CLI"""
        review_prompt = f"""Please review the following code changes.

{prompt}

Response format:
- Start with PASS or FAIL
- Explain the reason
"""
        result = await self.execute(review_prompt, context)

        if not result.success:
            return ReviewResult(passed=False, error_message=result.error_message)

        output = result.stdout.strip()
        passed = output.upper().startswith("PASS")

        return ReviewResult(passed=passed, feedback=output)
