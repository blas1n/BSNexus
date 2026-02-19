from unittest.mock import AsyncMock, patch

import pytest

from worker.git_ops import WorkerGitOps


@pytest.fixture
def git_ops() -> WorkerGitOps:
    return WorkerGitOps("/tmp/test-repo")


class TestEnsureRepo:
    async def test_ensure_repo_creates_new_repo(self, git_ops: WorkerGitOps) -> None:
        """ensure_repo() should init a new git repo when none exists."""
        with patch.object(git_ops, "_is_git_repo", return_value=False) as mock_check, \
             patch.object(git_ops, "_run", new_callable=AsyncMock) as mock_run, \
             patch("worker.git_ops.Path") as mock_path:
            mock_path.return_value.mkdir = lambda **kwargs: None
            await git_ops.ensure_repo()

        mock_check.assert_awaited_once()
        assert mock_run.await_count == 5  # init, config email, config name, checkout -b main, commit
        mock_run.assert_any_await("init", "/tmp/test-repo")
        mock_run.assert_any_await("config", "user.email", "bsnexus-worker@localhost")
        mock_run.assert_any_await("config", "user.name", "BSNexus Worker")
        mock_run.assert_any_await("checkout", "-b", "main")

    async def test_ensure_repo_skips_existing(self, git_ops: WorkerGitOps) -> None:
        """ensure_repo() should only verify main when repo already exists."""
        with patch.object(git_ops, "_is_git_repo", return_value=True) as mock_check, \
             patch.object(git_ops, "_run", new_callable=AsyncMock) as mock_run:
            await git_ops.ensure_repo()

        mock_check.assert_awaited_once()
        mock_run.assert_awaited_once_with("rev-parse", "--verify", "main")

    async def test_ensure_repo_recovers_partial_init(self, git_ops: WorkerGitOps) -> None:
        """ensure_repo() should create main + empty commit when repo exists but main has no commits."""
        with patch.object(git_ops, "_is_git_repo", return_value=True), \
             patch.object(git_ops, "_run", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = [
                RuntimeError("fatal: Needed a single revision"),  # rev-parse --verify main
                "",  # checkout -b main
                "",  # commit --allow-empty
            ]
            await git_ops.ensure_repo()

        assert mock_run.await_count == 3
        mock_run.assert_any_await("rev-parse", "--verify", "main")
        mock_run.assert_any_await("checkout", "-b", "main")
        mock_run.assert_any_await("commit", "--allow-empty", "-m", "chore: initialize repository")


class TestEnsureBranch:
    async def test_ensure_branch_creates_new(self, git_ops: WorkerGitOps) -> None:
        """ensure_branch() should create a new branch from main if it doesn't exist."""
        with patch.object(git_ops, "_run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = ""  # branch --list returns empty, rev-parse succeeds
            await git_ops.ensure_branch("phase/auth")

        mock_run.assert_any_await("branch", "--list", "phase/auth")
        mock_run.assert_any_await("rev-parse", "--verify", "main")
        mock_run.assert_any_await("checkout", "-b", "phase/auth", "main")

    async def test_ensure_branch_checks_out_existing(self, git_ops: WorkerGitOps) -> None:
        """ensure_branch() should checkout existing branch."""
        with patch.object(git_ops, "_run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "  phase/auth"  # branch --list returns match
            await git_ops.ensure_branch("phase/auth")

        mock_run.assert_any_await("branch", "--list", "phase/auth")
        mock_run.assert_any_await("checkout", "phase/auth")

    async def test_ensure_branch_fallback_no_main(self, git_ops: WorkerGitOps) -> None:
        """ensure_branch() should branch from HEAD when main is not a valid ref."""
        with patch.object(git_ops, "_run", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = [
                "",  # branch --list returns empty
                RuntimeError("fatal: 'main' is not a commit"),  # rev-parse --verify main
                "",  # checkout -b phase/auth (from HEAD)
            ]
            await git_ops.ensure_branch("phase/auth")

        mock_run.assert_any_await("branch", "--list", "phase/auth")
        mock_run.assert_any_await("rev-parse", "--verify", "main")
        mock_run.assert_any_await("checkout", "-b", "phase/auth")


class TestCommitTask:
    async def test_commit_task_returns_hash(self, git_ops: WorkerGitOps) -> None:
        """commit_task() should stage, commit, and return the commit hash."""
        with patch.object(git_ops, "ensure_branch", new_callable=AsyncMock), \
             patch.object(git_ops, "_run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "abc123def456"
            result = await git_ops.commit_task("task-1", "Add login", "phase/auth")

        assert result == "abc123def456"
        mock_run.assert_any_await("add", ".")
        mock_run.assert_any_await("commit", "-m", "feat(task-task-1): Add login", "--allow-empty")
        mock_run.assert_any_await("rev-parse", "HEAD")


class TestRevertTask:
    async def test_revert_task_calls_git_revert(self, git_ops: WorkerGitOps) -> None:
        """revert_task() should checkout branch and revert the commit."""
        with patch.object(git_ops, "ensure_branch", new_callable=AsyncMock) as mock_branch, \
             patch.object(git_ops, "_run", new_callable=AsyncMock) as mock_run:
            await git_ops.revert_task("abc123", "phase/auth")

        mock_branch.assert_awaited_once_with("phase/auth")
        mock_run.assert_any_await("revert", "--no-edit", "abc123")

    async def test_revert_task_skips_empty_hash(self, git_ops: WorkerGitOps) -> None:
        """revert_task() should be a no-op for empty commit hash."""
        with patch.object(git_ops, "ensure_branch", new_callable=AsyncMock) as mock_branch, \
             patch.object(git_ops, "_run", new_callable=AsyncMock) as mock_run:
            await git_ops.revert_task("", "phase/auth")

        mock_branch.assert_not_awaited()
        mock_run.assert_not_awaited()


class TestIsGitRepo:
    async def test_is_git_repo_true(self) -> None:
        """_is_git_repo() should return True for valid git repos."""
        git_ops = WorkerGitOps("/tmp/test")
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b".git", b""))

        with patch("worker.git_ops.asyncio.create_subprocess_exec", return_value=mock_process):
            assert await git_ops._is_git_repo() is True

    async def test_is_git_repo_false(self) -> None:
        """_is_git_repo() should return False for non-git dirs."""
        git_ops = WorkerGitOps("/tmp/test")
        mock_process = AsyncMock()
        mock_process.returncode = 128
        mock_process.communicate = AsyncMock(return_value=(b"", b"not a git repo"))

        with patch("worker.git_ops.asyncio.create_subprocess_exec", return_value=mock_process):
            assert await git_ops._is_git_repo() is False

    async def test_is_git_repo_file_not_found(self) -> None:
        """_is_git_repo() should return False when git command not found."""
        git_ops = WorkerGitOps("/tmp/test")

        with patch("worker.git_ops.asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            assert await git_ops._is_git_repo() is False
