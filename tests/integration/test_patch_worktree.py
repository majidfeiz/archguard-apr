import subprocess
from pathlib import Path

import pytest

from archguard.infrastructure.git_worktree import GitCandidateWorkspace, GitRepositoryState


def git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def git_repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "ArchGuard Test")
    (root / "a.py").write_text("old\n")
    git(root, "add", "a.py")
    git(root, "commit", "-m", "baseline")
    return root


def test_candidate_is_isolated_and_cleanup_is_complete(git_repository: Path) -> None:
    states, adapter = GitRepositoryState(), GitCandidateWorkspace()
    before = states.capture(git_repository)
    patch = (
        b"diff --git a/a.py b/a.py\nindex 3367afd..3e75765 100644\n"
        b"--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+new\n"
    )
    with adapter.workspace(git_repository, before.head_commit) as candidate:
        assert adapter.check_apply(candidate, patch)
        assert adapter.apply(candidate, patch)
        assert (candidate / "a.py").read_text() == "new\n"
        assert (git_repository / "a.py").read_text() == "old\n"
    assert states.capture(git_repository) == before
    assert len(git(git_repository, "worktree", "list", "--porcelain").split("worktree ")) == 2


def test_failed_application_and_exception_cleanup(git_repository: Path) -> None:
    adapter = GitCandidateWorkspace()
    head = git(git_repository, "rev-parse", "HEAD")
    with pytest.raises(RuntimeError):
        with adapter.workspace(git_repository, head) as candidate:
            assert not adapter.check_apply(candidate, b"bad")
            raise RuntimeError("analysis failed")
    assert "archguard-candidate-" not in git(git_repository, "worktree", "list", "--porcelain")


def test_dirty_repository_is_rejected(git_repository: Path) -> None:
    (git_repository / "untracked").write_text("x")
    with pytest.raises(ValueError, match="not clean"):
        GitRepositoryState().require_clean(git_repository)
