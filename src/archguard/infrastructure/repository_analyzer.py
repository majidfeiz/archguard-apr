"""Descriptor-relative, read-only local Python discovery and parsing."""

import errno
import hashlib
import os
import stat
import tokenize
from collections import Counter
from fnmatch import fnmatchcase
from io import BytesIO
from pathlib import Path

from archguard.application.services.repository import AnalysisError, UnsafePathError
from archguard.domain.enums import Severity
from archguard.domain.repository import (
    MESSAGES,
    SCHEMA_VERSION,
    AnalysisDiagnostic,
    AnalysisOptions,
    DiagnosticCode,
    ImportSnapshot,
    ParseStatus,
    RepositorySnapshot,
    SourceFileSnapshot,
    SymbolSnapshot,
    module_name,
    safe_path,
    summarize,
)
from archguard.infrastructure.python_parser import parse_source
from archguard.infrastructure.repository_codec import fingerprint


def validate_root(root: Path) -> Path:
    if root.is_symlink():
        raise UnsafePathError("repository root must not be a symlink")
    try:
        resolved = root.resolve(strict=True)
    except (OSError, RuntimeError):
        raise ValueError("repository root must be an existing directory") from None
    if not resolved.is_dir():
        raise ValueError("repository root must be an existing directory")
    if os.open not in os.supports_dir_fd or not hasattr(os, "O_NOFOLLOW"):
        raise UnsafePathError("safe descriptor-relative discovery is unsupported on this platform")
    return resolved


def physical_lines(raw: bytes) -> int:
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return normalized.count(b"\n") + int(bool(normalized) and not normalized.endswith(b"\n"))


class LocalRepositoryAnalyzer:
    def analyze(self, repository: Path, options: AnalysisOptions) -> RepositorySnapshot:
        root = validate_root(repository)
        diagnostics: list[AnalysisDiagnostic] = []
        files: list[SourceFileSnapshot] = []

        def report(
            path: str | None,
            code: DiagnosticCode,
            severity: Severity = Severity.ERROR,
            line: int | None = None,
            column: int | None = None,
        ) -> None:
            diagnostics.append(
                AnalysisDiagnostic(path, code, severity, MESSAGES[code], line, column)
            )
            if options.fail_fast and severity == Severity.ERROR:
                raise AnalysisError("analysis stopped at the first error diagnostic")

        def walk_error(error: OSError) -> None:
            # OS exception filenames can disclose absolute paths; never copy them into diagnostics.
            report(None, DiagnosticCode.DIRECTORY_UNREADABLE)

        def selected(path: str, name: str) -> bool:
            return (options.include_hidden or not name.startswith(".")) and not any(
                fnmatchcase(path, pattern) for pattern in options.excluded_patterns
            )

        def skipped(path: str, code: DiagnosticCode) -> None:
            if path.endswith(".py"):
                files.append(
                    SourceFileSnapshot(
                        path,
                        None,
                        0,
                        0,
                        module_name(path, options),
                        Path(path).name == "__init__.py",
                        ParseStatus.SKIPPED,
                    )
                )
            report(
                path,
                code,
                Severity.WARNING if code == DiagnosticCode.SKIPPED_SYMLINK else Severity.ERROR,
            )

        # fwalk protects directory descent; reads use its live directory descriptor.
        try:
            for directory, dirs, names, directory_fd in os.fwalk(
                root, follow_symlinks=False, onerror=walk_error
            ):
                relative = Path(directory).relative_to(root)
                directory_names = set(dirs)
                for name in sorted(dirs + names):
                    path = (relative / name).as_posix()
                    is_directory = name in directory_names
                    if (is_directory and name in options.excluded_dirs) or not selected(path, name):
                        if is_directory:
                            directory_names.discard(name)
                        continue
                    try:
                        safe_path(path)
                    except ValueError:
                        if is_directory:
                            directory_names.discard(name)
                        report(None, DiagnosticCode.PATH_POLICY_REJECTION)
                        continue
                    try:
                        info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                        if stat.S_ISLNK(info.st_mode):
                            if is_directory:
                                directory_names.discard(name)
                            if options.symlink_policy == "reject":
                                raise UnsafePathError("symbolic link rejected by analysis policy")
                            skipped(path, DiagnosticCode.SKIPPED_SYMLINK)
                            continue
                        if is_directory:
                            continue
                        if not name.endswith(".py"):
                            continue
                        if not stat.S_ISREG(info.st_mode):
                            skipped(path, DiagnosticCode.PATH_POLICY_REJECTION)
                            continue
                        if info.st_size > options.max_file_bytes:
                            skipped(path, DiagnosticCode.FILE_TOO_LARGE)
                            continue
                        descriptor = os.open(
                            name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd
                        )
                        with os.fdopen(descriptor, "rb") as source:
                            opened = os.fstat(source.fileno())
                            if not stat.S_ISREG(opened.st_mode):
                                skipped(path, DiagnosticCode.PATH_POLICY_REJECTION)
                                continue
                            raw = source.read(options.max_file_bytes + 1)
                        if len(raw) > options.max_file_bytes:
                            skipped(path, DiagnosticCode.FILE_TOO_LARGE)
                            continue
                    except OSError as error:
                        if is_directory:
                            directory_names.discard(name)
                            report(path, DiagnosticCode.DIRECTORY_UNREADABLE)
                        elif name.endswith(".py"):
                            code = (
                                DiagnosticCode.PATH_POLICY_REJECTION
                                if error.errno == errno.ELOOP
                                else DiagnosticCode.UNREADABLE_FILE
                            )
                            files.append(
                                SourceFileSnapshot(
                                    path,
                                    None,
                                    0,
                                    0,
                                    module_name(path, options),
                                    name == "__init__.py",
                                    ParseStatus.FAILED,
                                )
                            )
                            report(path, code)
                        continue
                    content_digest = hashlib.sha256(raw).hexdigest()
                    status = ParseStatus.PARSED
                    imports: tuple[ImportSnapshot, ...] = ()
                    symbols: tuple[SymbolSnapshot, ...] = ()
                    try:
                        encoding, _ = tokenize.detect_encoding(BytesIO(raw).readline)
                        text = raw.decode(encoding)
                    except (SyntaxError, UnicodeError, LookupError):
                        status = ParseStatus.FAILED
                        report(path, DiagnosticCode.UNSUPPORTED_ENCODING)
                    else:
                        try:
                            imports, symbols = parse_source(text, path)
                        except (SyntaxError, ValueError, RecursionError) as error:
                            status = ParseStatus.FAILED
                            line = error.lineno if isinstance(error, SyntaxError) else None
                            offset = error.offset if isinstance(error, SyntaxError) else None
                            report(
                                path,
                                DiagnosticCode.SYNTAX_ERROR,
                                line=line if line and line > 0 else None,
                                column=max(0, offset - 1) if offset else None,
                            )
                    files.append(
                        SourceFileSnapshot(
                            path,
                            content_digest,
                            len(raw),
                            physical_lines(raw),
                            module_name(path, options),
                            name == "__init__.py",
                            status,
                            imports,
                            symbols,
                        )
                    )
                dirs[:] = sorted(directory_names)
        except OSError:
            raise AnalysisError("repository discovery failed") from None
        counts = Counter(f.module_name for f in files if f.module_name is not None)
        for file in files:
            if file.module_name is None:
                report(file.path, DiagnosticCode.INVALID_MODULE, Severity.WARNING)
            elif counts[file.module_name] > 1:
                report(file.path, DiagnosticCode.MODULE_CONFLICT)
        ordered_files = tuple(sorted(files, key=lambda f: f.path))
        ordered_diagnostics = tuple(sorted(diagnostics, key=lambda d: d.sort_key))
        return RepositorySnapshot(
            SCHEMA_VERSION,
            "python",
            fingerprint(options, ordered_files),
            "repository",
            options,
            ordered_files,
            ordered_diagnostics,
            summarize(ordered_files, ordered_diagnostics),
        )
