"""Shared bounded artifact reads, destination policy and atomic byte writes."""

import hashlib
import os
import stat
import tempfile
from pathlib import Path, PureWindowsPath

from archguard.application.services.repository import UnsafePathError
from archguard.domain.repository import digest, safe_path


def destination_path(destination: Path) -> Path:
    if ".." in destination.parts or ".." in PureWindowsPath(str(destination)).parts:
        raise UnsafePathError("destination parent traversal is forbidden")
    if "\\" in str(destination) or destination.is_symlink():
        raise UnsafePathError("destination must not be a symlink or non-native path")
    try:
        safe_path(destination.name)
    except ValueError:
        raise UnsafePathError("destination filename violates path policy") from None
    try:
        parent = destination.parent.resolve(strict=True)
        if not parent.is_dir() or (destination.exists() and not destination.is_file()):
            raise UnsafePathError(
                "destination parent must exist and destination must be a regular file"
            )
        return parent / destination.name
    except (OSError, RuntimeError):
        raise UnsafePathError("destination parent is unavailable") from None


def atomic_write(target: Path, raw: bytes) -> None:
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target.parent, prefix=".archguard-", delete=False
        ) as file:
            temporary = file.name
            file.write(raw)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def read_artifact(source: Path, expected_sha256: str | None, limit: int) -> bytes:
    if source.is_symlink():
        raise UnsafePathError("artifact symlinks are not accepted")
    if not hasattr(os, "O_NOFOLLOW"):
        raise UnsafePathError("safe artifact reads are unsupported on this platform")
    descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as file:
        if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
            raise UnsafePathError("artifact must be a regular file")
        raw = file.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("snapshot exceeds the artifact size limit")
    if expected_sha256 is not None:
        digest(expected_sha256)
        if hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise ValueError("artifact SHA-256 mismatch")
    return raw
