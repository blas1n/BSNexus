import asyncio


class GitOps:
    """Git automation — Phase=branch, Task=commit mapping."""

    def __init__(self, repo_path: str = "/workspace"):
        self.repo_path = repo_path

    async def create_phase_branch(self, branch_name: str) -> None:
        """Create a branch when a Phase is created."""
        await self._run("checkout", "-b", branch_name)

    async def commit_task(self, task_id: str, title: str, phase_branch: str) -> str:
        """Commit when a Task is completed."""
        # Switch to phase branch
        await self._run("checkout", phase_branch)

        # Stage changes
        await self._run("add", ".")

        # Commit
        message = f"feat(task-{task_id}): {title}"
        await self._run("commit", "-m", message, "--allow-empty")

        # Return commit hash
        return await self._run("rev-parse", "HEAD")

    async def revert_task(self, commit_hash: str) -> None:
        """Revert a commit when a Task is rejected."""
        if commit_hash:
            await self._run("revert", "--no-edit", commit_hash)

    async def merge_phase(self, phase_branch: str, target_branch: str = "main") -> None:
        """Merge phase branch to target when Phase is completed."""
        await self._run("checkout", target_branch)
        await self._run("merge", phase_branch, "--no-ff")

    async def get_current_commit(self) -> str:
        """Get current commit hash."""
        return await self._run("rev-parse", "HEAD")

    async def _run(self, *args: str) -> str:
        """Execute a git command asynchronously."""
        process = await asyncio.create_subprocess_exec(
            "git", "-C", self.repo_path, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise RuntimeError(f"Git error: {stderr.decode()}")

        return stdout.decode().strip()
