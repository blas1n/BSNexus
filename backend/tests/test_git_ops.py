import pathlib
import subprocess

import pytest

from backend.src.core.git_ops import GitOps


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repository for testing."""
    repo = str(tmp_path)
    subprocess.run(["git", "init", repo], check=True, capture_output=True)
    subprocess.run(["git", "-C", repo, "config", "user.email", "test@test.com"], check=True, capture_output=True)
    subprocess.run(["git", "-C", repo, "config", "user.name", "Test"], check=True, capture_output=True)
    # Create initial commit on main branch
    subprocess.run(["git", "-C", repo, "checkout", "-b", "main"], check=True, capture_output=True)
    (tmp_path / "README.md").write_text("init")
    subprocess.run(["git", "-C", repo, "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", repo, "commit", "-m", "initial commit"], check=True, capture_output=True)
    return repo


async def test_create_phase_branch(git_repo: str) -> None:
    """Creates a branch and verifies it exists."""
    ops = GitOps(repo_path=git_repo)
    await ops.create_phase_branch("phase/design")

    # Verify branch exists by listing branches
    result = subprocess.run(
        ["git", "-C", git_repo, "branch", "--list", "phase/design"],
        capture_output=True, text=True, check=True,
    )
    assert "phase/design" in result.stdout


async def test_commit_task(git_repo: str) -> None:
    """Commits and verifies commit message format feat(task-{id}): {title}."""
    ops = GitOps(repo_path=git_repo)
    await ops.create_phase_branch("phase/backend")

    # Create a file to commit
    (pathlib.Path(git_repo) / "task_file.py").write_text("print('hello')")

    await ops.commit_task("42", "implement login", "phase/backend")

    # Verify commit message format
    result = subprocess.run(
        ["git", "-C", git_repo, "log", "-1", "--format=%s"],
        capture_output=True, text=True, check=True,
    )
    assert result.stdout.strip() == "feat(task-42): implement login"


async def test_commit_task_returns_hash(git_repo: str) -> None:
    """Verifies returned hash matches HEAD."""
    ops = GitOps(repo_path=git_repo)
    await ops.create_phase_branch("phase/api")

    commit_hash = await ops.commit_task("1", "add endpoint", "phase/api")

    # Verify the returned hash matches HEAD
    result = subprocess.run(
        ["git", "-C", git_repo, "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    )
    assert commit_hash == result.stdout.strip()
    assert len(commit_hash) == 40  # Full SHA-1 hash


async def test_revert_task(git_repo: str) -> None:
    """Commits, then reverts, verifies revert commit exists."""
    ops = GitOps(repo_path=git_repo)
    await ops.create_phase_branch("phase/feature")

    # Make a commit
    (pathlib.Path(git_repo) / "feature.py").write_text("code")
    commit_hash = await ops.commit_task("5", "add feature", "phase/feature")

    # Revert the commit
    await ops.revert_task(commit_hash)

    # Verify revert commit exists
    result = subprocess.run(
        ["git", "-C", git_repo, "log", "-1", "--format=%s"],
        capture_output=True, text=True, check=True,
    )
    assert "Revert" in result.stdout


async def test_revert_task_empty_hash(git_repo: str) -> None:
    """Passing empty string does nothing (no error)."""
    ops = GitOps(repo_path=git_repo)
    # Should not raise any error
    await ops.revert_task("")


async def test_merge_phase(git_repo: str) -> None:
    """Creates branch, commits, merges to main, verifies merge commit."""
    ops = GitOps(repo_path=git_repo)
    await ops.create_phase_branch("phase/merge-test")

    # Make a commit on the phase branch
    (pathlib.Path(git_repo) / "merged_file.py").write_text("merged content")
    await ops.commit_task("10", "mergeable work", "phase/merge-test")

    # Merge back to main
    await ops.merge_phase("phase/merge-test", "main")

    # Verify we are on main
    result = subprocess.run(
        ["git", "-C", git_repo, "branch", "--show-current"],
        capture_output=True, text=True, check=True,
    )
    assert result.stdout.strip() == "main"

    # Verify merge commit exists (--no-ff creates a merge commit)
    result = subprocess.run(
        ["git", "-C", git_repo, "log", "-1", "--format=%s"],
        capture_output=True, text=True, check=True,
    )
    assert "Merge branch" in result.stdout or "phase/merge-test" in result.stdout


async def test_get_current_commit(git_repo: str) -> None:
    """Returns valid commit hash."""
    ops = GitOps(repo_path=git_repo)
    commit_hash = await ops.get_current_commit()

    # Verify it's a valid 40-char hex hash
    assert len(commit_hash) == 40
    assert all(c in "0123456789abcdef" for c in commit_hash)


async def test_run_error(git_repo: str) -> None:
    """Invalid git command raises RuntimeError."""
    ops = GitOps(repo_path=git_repo)
    with pytest.raises(RuntimeError, match="Git error"):
        await ops._run("not-a-real-command")


async def test_create_phase_branch_already_exists(git_repo: str) -> None:
    """Creating existing branch raises RuntimeError."""
    ops = GitOps(repo_path=git_repo)
    await ops.create_phase_branch("phase/duplicate")

    # Switch back to main so we can try creating same branch again
    await ops._run("checkout", "main")

    with pytest.raises(RuntimeError, match="Git error"):
        await ops.create_phase_branch("phase/duplicate")
