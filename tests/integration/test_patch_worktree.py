import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

from archguard.infrastructure.git_worktree import (
    MAX_GIT_OUTPUT_BYTES,
    GitCandidateWorkspace,
    GitOperationError,
    GitRepositoryState,
    _git,
)


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
    before = GitRepositoryState().capture(git_repository)
    (git_repository / "untracked").write_text("changed")
    after = GitRepositoryState().capture(git_repository)
    assert before.untracked_status_sha256 == after.untracked_status_sha256
    assert before.untracked_content_sha256 != after.untracked_content_sha256
    with pytest.raises(ValueError, match="not clean"):
        GitRepositoryState().require_clean(git_repository)


def test_hooks_are_suppressed(git_repository: Path, tmp_path: Path) -> None:
    marker = tmp_path / "hook-ran"
    hook = git_repository / ".git/hooks/post-checkout"
    hook.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
    hook.chmod(0o755)
    with GitCandidateWorkspace().workspace(
        git_repository, git(git_repository, "rev-parse", "HEAD")
    ):
        pass
    assert not marker.exists()


def test_timeout_and_output_limits_are_normalized(
    git_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def timeout(*args: object, **kwargs: object) -> object:
        raise subprocess.TimeoutExpired("git", 1)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(GitOperationError, match="bounded Git operation failed"):
        _git(git_repository, ["status"])

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args, 0, stdout=b"x" * (MAX_GIT_OUTPUT_BYTES + 1), stderr=b""
        ),
    )
    with pytest.raises(GitOperationError, match="output exceeded"):
        _git(git_repository, ["status"])


def test_timeout_after_registration_still_cleans_worktree(
    git_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_run: Any = subprocess.run

    def checkout_timeout(arguments: list[str], **kwargs: object) -> object:
        if "checkout" in arguments:
            raise subprocess.TimeoutExpired("git checkout", 1)
        return real_run(arguments, **kwargs)

    monkeypatch.setattr(subprocess, "run", checkout_timeout)
    with pytest.raises(GitOperationError):
        with GitCandidateWorkspace().workspace(
            git_repository, git(git_repository, "rev-parse", "HEAD")
        ):
            pass
    assert "archguard-candidate-" not in git(git_repository, "worktree", "list", "--porcelain")


def test_cleanup_is_idempotent_and_rejects_unowned_targets(git_repository: Path) -> None:
    adapter = GitCandidateWorkspace()
    parent = Path(tempfile.mkdtemp(prefix="archguard-candidate-"))
    candidate = parent / "worktree"
    adapter._cleanup(git_repository, parent, candidate, False)
    adapter._cleanup(git_repository, parent, candidate, False)
    with pytest.raises(GitOperationError, match="safety validation"):
        adapter._cleanup(git_repository, git_repository, git_repository / "x", False)


def test_partial_worktree_creation_failure_removes_temporary_parent(
    git_repository: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "archguard-candidate-partial"
    monkeypatch.setattr(tempfile, "mkdtemp", lambda **kwargs: str(parent))
    with pytest.raises(GitOperationError):
        with GitCandidateWorkspace().workspace(git_repository, "0" * 40):
            pass
    assert not parent.exists()
    assert "archguard-candidate-partial" not in git(
        git_repository, "worktree", "list", "--porcelain"
    )


def test_submodule_is_not_initialized(tmp_path: Path) -> None:
    child = tmp_path / "child"
    child.mkdir()
    git(child, "init", "-b", "main")
    git(child, "config", "user.email", "test@example.invalid")
    git(child, "config", "user.name", "ArchGuard Test")
    (child / "payload").write_text("not executed")
    git(child, "add", "payload")
    git(child, "commit", "-m", "child")
    parent = tmp_path / "parent"
    parent.mkdir()
    git(parent, "init", "-b", "main")
    git(parent, "config", "user.email", "test@example.invalid")
    git(parent, "config", "user.name", "ArchGuard Test")
    subprocess.run(
        [
            "git",
            "-c",
            "protocol.file.allow=always",
            "-C",
            str(parent),
            "submodule",
            "add",
            str(child),
            "vendor",
        ],
        check=True,
        capture_output=True,
    )
    git(parent, "commit", "-am", "submodule")
    with GitCandidateWorkspace().workspace(parent, git(parent, "rev-parse", "HEAD")) as candidate:
        assert (candidate / "vendor").is_dir()
        assert not (candidate / "vendor/payload").exists()
