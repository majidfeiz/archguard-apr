"""Descriptor-relative snapshot-bound UTF-8 excerpt reads."""

import hashlib
import os
import stat
from pathlib import Path

from archguard.domain.context import SourceExcerpt
from archguard.domain.repository import RepositorySnapshot, safe_path
from archguard.infrastructure.repository_analyzer import validate_root

MAX_SOURCE_LINE_BYTES = 65_536


class SourceIdentityError(ValueError):
    """The working file no longer matches the validated snapshot."""


class LocalSourceExcerptReader:
    def read(
        self,
        repository: Path,
        snapshot: RepositorySnapshot,
        path: str,
        line_start: int,
        line_end: int,
    ) -> SourceExcerpt:
        safe_path(path)
        source = next((item for item in snapshot.files if item.path == path), None)
        if source is None or source.sha256 is None:
            raise SourceIdentityError("source is absent from the validated snapshot")
        if not any(
            path == root or path.startswith(root + "/")
            for root in snapshot.analysis_options.source_roots
        ):
            raise SourceIdentityError("source is outside validated source roots")
        if not (1 <= line_start <= line_end <= source.line_count):
            raise ValueError("excerpt range exceeds validated source")
        root = validate_root(repository)
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        descriptor: int | None = None
        current = root_fd
        try:
            parts = path.split("/")
            for part in parts[:-1]:
                next_fd = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current
                )
                if current != root_fd:
                    os.close(current)
                current = next_fd
            descriptor = os.open(
                parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=current
            )
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_size > source.byte_size:
                raise SourceIdentityError("source type or size changed after snapshot")
            with os.fdopen(descriptor, "rb") as stream:
                descriptor = None
                raw = stream.read(source.byte_size + 1)
        except OSError:
            raise SourceIdentityError("source could not be safely reopened") from None
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if current != root_fd:
                os.close(current)
            os.close(root_fd)
        if len(raw) != source.byte_size or hashlib.sha256(raw).hexdigest() != source.sha256:
            raise SourceIdentityError("source identity changed after snapshot")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise SourceIdentityError("source is not UTF-8") from None
        lines = text.splitlines(keepends=True)
        selected = lines[line_start - 1 : line_end]
        if any(len(line.encode("utf-8")) > MAX_SOURCE_LINE_BYTES for line in selected):
            raise SourceIdentityError("source line exceeds safety limit")
        content = "".join(selected)
        content_raw = content.encode("utf-8")
        return SourceExcerpt(
            path,
            line_start,
            line_end,
            len(content_raw),
            hashlib.sha256(content_raw).hexdigest(),
            content,
        )
