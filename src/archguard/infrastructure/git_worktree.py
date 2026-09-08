"""Non-interactive Git state proof and isolated detached-worktree lifecycle."""

import hashlib
import os
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from archguard.domain.patch_validation import RepositoryStateProof

GIT_TIMEOUT_SECONDS = 30
MAX_GIT_OUTPUT_BYTES = 1024 * 1024


class GitOperationError(RuntimeError):
    """A bounded Git operation failed without exposing raw command output."""


def _git(
    repository: Path, arguments: list[str], stdin: bytes | None = None, check: bool = True
) -> subprocess.CompletedProcess[bytes]:
    environment = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.hooksPath",
        "GIT_CONFIG_VALUE_0": os.devnull,
    }
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            input=stdin,
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise GitOperationError("bounded Git operation failed") from None
    if len(result.stdout) > MAX_GIT_OUTPUT_BYTES or len(result.stderr) > MAX_GIT_OUTPUT_BYTES:
        raise GitOperationError("Git output exceeded the safety limit")
    if check and result.returncode:
        raise GitOperationError("bounded Git operation failed")
    return result


class GitRepositoryState:
    def resolve_commit(self, repository: Path, revision: str) -> str:
        if not revision or revision.startswith("-"):
            raise ValueError("invalid baseline revision")
        value = (
            _git(repository, ["rev-parse", "--verify", revision + "^{commit}"])
            .stdout.decode("ascii")
            .strip()
        )
        if len(value) != 40:
            raise GitOperationError("Git returned an invalid commit identity")
        return value

    def capture(self, repository: Path) -> RepositoryStateProof:
        head = self.resolve_commit(repository, "HEAD")
        branch_result = _git(
            repository, ["symbolic-ref", "--quiet", "--short", "HEAD"], check=False
        )
        branch = (
            branch_result.stdout.decode("utf-8").strip() if branch_result.returncode == 0 else None
        )
        index_tree = hashlib.sha256(_git(repository, ["write-tree"]).stdout).hexdigest()
        tracked = _git(repository, ["status", "--porcelain=v1", "--untracked-files=no"]).stdout
        untracked = _git(repository, ["ls-files", "--others", "--exclude-standard", "-z"]).stdout
        return RepositoryStateProof(
            head,
            branch,
            index_tree,
            hashlib.sha256(tracked).hexdigest(),
            hashlib.sha256(untracked).hexdigest(),
            self._untracked_content(repository, untracked),
        )

    @staticmethod
    def _untracked_content(repository: Path, paths: bytes) -> str:
        fingerprint = hashlib.sha256()
        for encoded in sorted(filter(None, paths.split(b"\0"))):
            try:
                target = repository / encoded.decode("utf-8", "surrogateescape")
                info = target.lstat()
                fingerprint.update(
                    encoded + b"\0" + str(stat.S_IFMT(info.st_mode)).encode() + b"\0"
                )
                if stat.S_ISREG(info.st_mode):
                    descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                    with os.fdopen(descriptor, "rb") as stream:
                        while chunk := stream.read(1024 * 1024):
                            fingerprint.update(chunk)
                elif stat.S_ISLNK(info.st_mode):
                    fingerprint.update(os.readlink(target).encode("utf-8", "surrogateescape"))
            except (OSError, UnicodeError):
                raise GitOperationError("untracked repository state could not be proven") from None
            fingerprint.update(b"\0")
        return fingerprint.hexdigest()

    def require_clean(self, repository: Path) -> RepositoryStateProof:
        proof = self.capture(repository)
        empty = hashlib.sha256(b"").hexdigest()
        if proof.tracked_status_sha256 != empty or proof.untracked_status_sha256 != empty:
            raise ValueError("original repository is not clean")
        return proof


class GitCandidateWorkspace:
    @staticmethod
    def _safe_parent(parent: Path) -> bool:
        try:
            return (
                parent.name.startswith("archguard-candidate-")
                and parent.parent.resolve() == Path(tempfile.gettempdir()).resolve()
                and (not parent.exists() or (parent.is_dir() and not parent.is_symlink()))
            )
        except (OSError, RuntimeError):
            return False

    def _cleanup(self, repository: Path, parent: Path, candidate: Path, created: bool) -> None:
        if not self._safe_parent(parent):
            raise GitOperationError("candidate cleanup target failed safety validation")
        if created:
            _git(repository, ["worktree", "remove", "--force", str(candidate)], check=False)
        if parent.exists():
            shutil.rmtree(parent)
        registered = _git(repository, ["worktree", "list", "--porcelain"]).stdout
        if str(candidate).encode() in registered or parent.exists():
            raise GitOperationError("candidate worktree cleanup failed")

    @contextmanager
    def workspace(self, repository: Path, baseline_commit: str) -> Iterator[Path]:
        parent = Path(tempfile.mkdtemp(prefix="archguard-candidate-"))
        candidate = parent / "worktree"
        created = False
        try:
            _git(
                repository,
                ["worktree", "add", "--detach", "--no-checkout", str(candidate), baseline_commit],
            )
            created = True
            _git(candidate, ["checkout", "--detach", baseline_commit])
            yield candidate
        finally:
            self._cleanup(repository, parent, candidate, created)

    def check_apply(self, workspace: Path, raw: bytes) -> bool:
        return (
            _git(
                workspace, ["apply", "--check", "--whitespace=nowarn", "-"], raw, check=False
            ).returncode
            == 0
        )

    def apply(self, workspace: Path, raw: bytes) -> bool:
        return (
            _git(workspace, ["apply", "--whitespace=nowarn", "-"], raw, check=False).returncode == 0
        )
