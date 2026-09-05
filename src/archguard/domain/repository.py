"""Canonical repository values: no I/O, frameworks, source text or host identity."""

import keyword
import re
from collections import Counter
from dataclasses import dataclass, fields
from enum import StrEnum
from pathlib import PurePosixPath

from archguard.domain.enums import Severity
from archguard.domain.models import relative_path

SCHEMA_VERSION = "1"
DEFAULT_EXCLUDED_DIRS = (
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    "build",
    "dist",
    "site-packages",
    "node_modules",
    "benchmark_checkouts",
    "benchmark checkouts",
)


class ParseStatus(StrEnum):
    PARSED = "parsed"
    FAILED = "failed"
    SKIPPED = "skipped"


class SymbolKind(StrEnum):
    CLASS = "class"
    FUNCTION = "function"
    ASYNC_FUNCTION = "async_function"


class Visibility(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    PRIVATE = "private"


class MethodKind(StrEnum):
    INSTANCE = "instance"
    CLASS = "class"
    STATIC = "static"
    PROPERTY = "property"
    NOT_APPLICABLE = "not_applicable"


class ImportKind(StrEnum):
    IMPORT = "import"
    FROM = "from"


class DiagnosticCode(StrEnum):
    SYNTAX_ERROR = "syntax_error"
    UNREADABLE_FILE = "unreadable_file"
    UNSUPPORTED_ENCODING = "unsupported_encoding"
    SKIPPED_SYMLINK = "skipped_symlink"
    FILE_TOO_LARGE = "file_too_large"
    PATH_POLICY_REJECTION = "path_policy_rejection"
    INVALID_MODULE = "invalid_module"
    MODULE_CONFLICT = "module_conflict"
    DIRECTORY_UNREADABLE = "directory_unreadable"


MESSAGES = {
    DiagnosticCode.SYNTAX_ERROR: "Python syntax could not be parsed.",
    DiagnosticCode.UNREADABLE_FILE: "Source could not be read safely.",
    DiagnosticCode.UNSUPPORTED_ENCODING: "Python source encoding could not be decoded.",
    DiagnosticCode.SKIPPED_SYMLINK: "Symbolic link was not followed.",
    DiagnosticCode.FILE_TOO_LARGE: "Source exceeds the configured byte limit.",
    DiagnosticCode.PATH_POLICY_REJECTION: "Path or file type violates the analysis policy.",
    DiagnosticCode.INVALID_MODULE: "Path does not derive an unambiguous Python module name.",
    DiagnosticCode.MODULE_CONFLICT: "Multiple files derive the same module name.",
    DiagnosticCode.DIRECTORY_UNREADABLE: "A directory could not be enumerated safely.",
}


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def safe_path(value: str) -> None:
    check(relative_path(value) == value, "path must be normalized")
    check(
        not any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in value),
        "path contains unsupported characters",
    )


def digest(value: str) -> None:
    check(re.fullmatch(r"[0-9a-f]{64}", value) is not None, "invalid SHA-256")


def dotted_name(value: str) -> bool:
    return bool(value) and all(
        part.isidentifier() and not keyword.iskeyword(part) for part in value.split(".")
    )


def visibility(name: str) -> Visibility:
    if name.startswith("__") and not name.endswith("__"):
        return Visibility.PRIVATE
    return Visibility.INTERNAL if name.startswith("_") else Visibility.PUBLIC


@dataclass(frozen=True)
class AnalysisOptions:
    max_file_bytes: int = 1_048_576
    excluded_dirs: tuple[str, ...] = DEFAULT_EXCLUDED_DIRS
    excluded_patterns: tuple[str, ...] = ("experiments/results", "experiments/results/*")
    source_roots: tuple[str, ...] = ()
    include_hidden: bool = False
    symlink_policy: str = "skip"
    fail_fast: bool = False

    def __post_init__(self) -> None:
        check(self.max_file_bytes > 0, "maximum source size must be positive")
        check(self.symlink_policy in {"skip", "reject"}, "unsupported symlink policy")
        for field in ("excluded_dirs", "excluded_patterns", "source_roots"):
            object.__setattr__(self, field, tuple(sorted(set(getattr(self, field)))))
        for name in self.excluded_dirs:
            safe_path(name)
            check("/" not in name, "excluded directory names must be single components")
        for pattern in self.excluded_patterns:
            safe_path(pattern)
        for root in self.source_roots:
            safe_path(root)


def module_name(path: str, options: AnalysisOptions) -> str | None:
    parts = PurePosixPath(path).parts
    matches = [
        PurePosixPath(root).parts
        for root in options.source_roots
        if parts[: len(PurePosixPath(root).parts)] == PurePosixPath(root).parts
    ]
    if matches:
        parts = parts[len(max(matches, key=len)) :]
    if not parts:
        return None
    components = list(parts[:-1]) + [PurePosixPath(parts[-1]).stem]
    if components[-1] == "__init__":
        components.pop()
    name = ".".join(components)
    return name if dotted_name(name) else None


def symbol_id(path: str, qualified_name: str, line: int, column: int) -> str:
    # File paths separate conflicting modules; spans distinguish redefinitions.
    return f"symbol:{path}:{qualified_name}@{line}:{column}"


@dataclass(frozen=True)
class SymbolSnapshot:
    identifier: str
    qualified_name: str
    kind: SymbolKind
    path: str
    start_line: int
    end_line: int
    column: int
    parent_qualified_name: str | None
    visibility: Visibility
    decorators: tuple[str, ...]
    method: MethodKind

    def __post_init__(self) -> None:
        safe_path(self.path)
        check(dotted_name(self.qualified_name), "invalid qualified name")
        check(1 <= self.start_line <= self.end_line and self.column >= 0, "invalid source span")
        check(
            self.identifier
            == symbol_id(self.path, self.qualified_name, self.start_line, self.column),
            "invalid symbol identifier",
        )
        expected_parent = self.qualified_name.rpartition(".")[0] or None
        check(self.parent_qualified_name == expected_parent, "invalid symbol parent")
        check(
            self.visibility == visibility(self.qualified_name.split(".")[-1]), "invalid visibility"
        )
        object.__setattr__(self, "decorators", tuple(self.decorators))
        check(all(dotted_name(name) for name in self.decorators), "invalid decorator name")
        check(
            self.kind != SymbolKind.CLASS or self.method == MethodKind.NOT_APPLICABLE,
            "class cannot have method classification",
        )


@dataclass(frozen=True)
class ImportSnapshot:
    path: str
    line: int
    column: int
    kind: ImportKind
    raw_module: str
    imported_name: str | None
    alias: str | None
    relative_level: int
    target: str
    wildcard: bool
    type_checking: bool

    def __post_init__(self) -> None:
        safe_path(self.path)
        check(
            self.line > 0 and self.column >= 0 and self.relative_level >= 0, "invalid import span"
        )
        check(not self.raw_module or dotted_name(self.raw_module), "invalid import module")
        check(
            self.alias is None or (self.alias.isidentifier() and not keyword.iskeyword(self.alias)),
            "invalid import alias",
        )
        if self.kind == ImportKind.IMPORT:
            check(
                bool(self.raw_module) and self.imported_name is None and self.relative_level == 0,
                "invalid plain import",
            )
            expected = self.raw_module
        else:
            check(
                self.imported_name == "*" or dotted_name(self.imported_name or ""),
                "invalid imported name",
            )
            check(bool(self.raw_module) or self.relative_level > 0, "invalid from import")
            expected = "." * self.relative_level + self.raw_module
            expected += ("." if self.raw_module else "") + str(self.imported_name)
        check(
            self.target == expected and self.wildcard == (self.imported_name == "*"),
            "invalid normalized import target",
        )


@dataclass(frozen=True)
class AnalysisDiagnostic:
    path: str | None
    code: DiagnosticCode
    severity: Severity
    message: str
    line: int | None = None
    column: int | None = None

    def __post_init__(self) -> None:
        if self.path is not None:
            safe_path(self.path)
        check(self.message == MESSAGES[self.code], "diagnostic must use a source-free message")
        check(self.line is None or self.line > 0, "invalid diagnostic line")
        check(self.column is None or self.column >= 0, "invalid diagnostic column")

    @property
    def sort_key(self) -> tuple[str, str, int, int]:
        return self.path or "", self.code.value, self.line or 0, self.column or 0


@dataclass(frozen=True)
class SourceFileSnapshot:
    path: str
    sha256: str | None
    byte_size: int
    line_count: int
    module_name: str | None
    package_initializer: bool
    parse_status: ParseStatus
    imports: tuple[ImportSnapshot, ...] = ()
    symbols: tuple[SymbolSnapshot, ...] = ()

    def __post_init__(self) -> None:
        safe_path(self.path)
        check(self.path.endswith(".py"), "source must have .py suffix")
        check(self.byte_size >= 0 and self.line_count >= 0, "invalid source counts")
        if self.sha256 is not None:
            digest(self.sha256)
        else:
            check(self.byte_size == 0 and self.line_count == 0, "unread source has no byte counts")
        check(
            self.parse_status != ParseStatus.PARSED or self.sha256 is not None,
            "parsed source requires digest",
        )
        check(self.module_name is None or dotted_name(self.module_name), "invalid module name")
        check(
            self.package_initializer == (PurePosixPath(self.path).name == "__init__.py"),
            "invalid initializer flag",
        )
        object.__setattr__(self, "imports", tuple(self.imports))
        object.__setattr__(self, "symbols", tuple(self.symbols))
        check(
            self.parse_status == ParseStatus.PARSED or not (self.imports or self.symbols),
            "unparsed source cannot contain AST records",
        )
        check(
            all(item.path == self.path and item.line <= self.line_count for item in self.imports),
            "import does not belong to source",
        )
        check(
            all(
                item.path == self.path and item.end_line <= self.line_count for item in self.symbols
            ),
            "symbol does not belong to source",
        )
        check(
            tuple(sorted(self.imports, key=lambda i: (i.line, i.column, i.target, i.alias or "")))
            == self.imports,
            "imports must be ordered",
        )
        check(
            tuple(sorted(self.symbols, key=lambda s: (s.start_line, s.column, s.identifier)))
            == self.symbols,
            "symbols must be ordered",
        )
        check(len({s.identifier for s in self.symbols}) == len(self.symbols), "duplicate symbol ID")
        stack: list[SymbolSnapshot] = []
        for symbol in self.symbols:
            while stack and symbol.start_line > stack[-1].end_line:
                stack.pop()
            parent = stack[-1] if stack else None
            check(
                symbol.parent_qualified_name == (parent.qualified_name if parent else None),
                "symbol parent or containment mismatch",
            )
            is_method = (
                parent is not None
                and parent.kind == SymbolKind.CLASS
                and symbol.kind != SymbolKind.CLASS
            )
            check(
                (symbol.method != MethodKind.NOT_APPLICABLE) == is_method, "method parent mismatch"
            )
            if parent is not None:
                check(symbol.end_line <= parent.end_line, "child span exceeds parent")
            stack.append(symbol)


@dataclass(frozen=True)
class RepositorySummary:
    discovered_python_files: int
    parsed_files: int
    failed_files: int
    skipped_files: int
    total_bytes: int
    total_lines: int
    module_count: int
    class_count: int
    function_count: int
    async_function_count: int
    import_statement_count: int
    diagnostic_count: int

    def __post_init__(self) -> None:
        check(
            all(getattr(self, f.name) >= 0 for f in fields(self)),
            "summary counts cannot be negative",
        )


def summarize(
    files: tuple[SourceFileSnapshot, ...], diagnostics: tuple[AnalysisDiagnostic, ...]
) -> RepositorySummary:
    symbols = [s for f in files for s in f.symbols]
    return RepositorySummary(
        len(files),
        sum(f.parse_status == ParseStatus.PARSED for f in files),
        sum(f.parse_status == ParseStatus.FAILED for f in files),
        sum(f.parse_status == ParseStatus.SKIPPED for f in files),
        sum(f.byte_size for f in files),
        sum(f.line_count for f in files),
        len({f.module_name for f in files if f.module_name is not None}),
        sum(s.kind == SymbolKind.CLASS for s in symbols),
        sum(s.kind == SymbolKind.FUNCTION for s in symbols),
        sum(s.kind == SymbolKind.ASYNC_FUNCTION for s in symbols),
        len({(i.path, i.line, i.column) for f in files for i in f.imports}),
        len(diagnostics),
    )


@dataclass(frozen=True)
class RepositorySnapshot:
    schema_version: str
    language: str
    repository_fingerprint: str
    root_label: str
    analysis_options: AnalysisOptions
    files: tuple[SourceFileSnapshot, ...]
    diagnostics: tuple[AnalysisDiagnostic, ...]
    summary: RepositorySummary

    def __post_init__(self) -> None:
        check(
            self.schema_version == SCHEMA_VERSION and self.language == "python",
            "unsupported schema",
        )
        check(self.root_label == "repository", "root label must not identify the host checkout")
        digest(self.repository_fingerprint)
        object.__setattr__(self, "files", tuple(self.files))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        paths = [f.path for f in self.files]
        check(paths == sorted(set(paths)), "source paths must be unique and sorted")
        check(
            tuple(sorted(self.diagnostics, key=lambda d: d.sort_key)) == self.diagnostics,
            "diagnostics must be ordered",
        )
        check(self.summary == summarize(self.files, self.diagnostics), "summary mismatch")
        check(
            all(f.module_name == module_name(f.path, self.analysis_options) for f in self.files),
            "module derivation mismatch",
        )
        module_counts = Counter(f.module_name for f in self.files if f.module_name is not None)
        by_path: dict[str | None, set[DiagnosticCode]] = {}
        for diagnostic in self.diagnostics:
            by_path.setdefault(diagnostic.path, set()).add(diagnostic.code)
            warning = diagnostic.code in {
                DiagnosticCode.SKIPPED_SYMLINK,
                DiagnosticCode.INVALID_MODULE,
            }
            check(
                diagnostic.severity == (Severity.WARNING if warning else Severity.ERROR),
                "diagnostic severity mismatch",
            )
        for file in self.files:
            codes = by_path.get(file.path, set())
            check(
                (file.module_name is None) == (DiagnosticCode.INVALID_MODULE in codes),
                "missing or spurious invalid-module diagnostic",
            )
            check(
                (file.module_name is not None and module_counts[file.module_name] > 1)
                == (DiagnosticCode.MODULE_CONFLICT in codes),
                "missing or spurious module-conflict diagnostic",
            )
            if file.parse_status == ParseStatus.FAILED:
                check(
                    bool(
                        codes
                        & {
                            DiagnosticCode.SYNTAX_ERROR,
                            DiagnosticCode.UNREADABLE_FILE,
                            DiagnosticCode.UNSUPPORTED_ENCODING,
                            DiagnosticCode.PATH_POLICY_REJECTION,
                        }
                    ),
                    "failed source requires a diagnostic",
                )
            if file.parse_status == ParseStatus.SKIPPED:
                check(
                    file.sha256 is None
                    and bool(
                        codes
                        & {
                            DiagnosticCode.SKIPPED_SYMLINK,
                            DiagnosticCode.FILE_TOO_LARGE,
                            DiagnosticCode.PATH_POLICY_REJECTION,
                        }
                    ),
                    "skipped source requires a diagnostic and no digest",
                )

    @property
    def partial(self) -> bool:
        return bool(self.diagnostics)
