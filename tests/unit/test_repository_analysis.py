import hashlib
import os
import shutil
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from archguard.application.services.repository import AnalysisError, UnsafePathError
from archguard.domain.repository import (
    AnalysisOptions,
    DiagnosticCode,
    MethodKind,
    ParseStatus,
    Visibility,
    module_name,
)
from archguard.infrastructure.repository_analyzer import LocalRepositoryAnalyzer, physical_lines
from archguard.infrastructure.repository_codec import canonical_snapshot, fingerprint

pytestmark = pytest.mark.unit


def write(root: Path, name: str, data: bytes = b"value = 1\n") -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def symlink(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")


def manifest(root: Path) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            label = path.relative_to(root).as_posix()
            if path.is_symlink():
                result[label] = ("symlink", os.readlink(path))
            elif path.is_dir():
                result[label] = ("directory", "")
            else:
                result[label] = ("file", hashlib.sha256(path.read_bytes()).hexdigest())
    return result


def test_structural_extraction(tmp_path: Path, repository_root: Path) -> None:
    source = (repository_root / "tests/fixtures/repositories/structure.py.txt").read_bytes()
    write(tmp_path, "package/module.py", source)
    snapshot = LocalRepositoryAnalyzer().analyze(tmp_path, AnalysisOptions())
    file = snapshot.files[0]
    assert file.parse_status == ParseStatus.PARSED
    assert file.sha256 == hashlib.sha256(source).hexdigest()
    assert file.module_name == "package.module"
    symbols = {symbol.qualified_name: symbol for symbol in file.symbols}
    assert symbols["Public.__private.inner"].parent_qualified_name == "Public.__private"
    assert symbols["Public.__private"].visibility == Visibility.PRIVATE
    assert symbols["_internal"].visibility == Visibility.INTERNAL
    assert symbols["Public"].decorators == ("module.decorator",)
    assert symbols["asynchronous"].decorators == ("factory.attribute",)
    assert symbols["unknown_decorator"].decorators == ()
    assert symbols["unknown_attribute"].decorators == ()
    assert symbols["Public.static"].method == MethodKind.STATIC
    assert symbols["Public.make"].method == MethodKind.CLASS
    assert symbols["Public.value"].method == MethodKind.PROPERTY
    assert symbols["Public.work"].method == MethodKind.INSTANCE
    assert symbols["Public.__private.inner"].method == MethodKind.NOT_APPLICABLE
    assert (
        symbols["Public"].start_line
        < symbols["Public.Nested"].end_line
        < symbols["Public"].end_line
    )
    duplicates = [s.identifier for s in file.symbols if s.qualified_name == "duplicate"]
    assert len(set(duplicates)) == 2
    imports = {item.target: item for item in file.imports}
    assert imports["os"].alias == "operating_system"
    assert imports[".sibling"].relative_level == 1
    assert imports[".sibling"].alias == "sibling_alias"
    assert imports["..parent.Thing"].relative_level == 2
    assert imports["external.*"].wildcard
    assert imports["annotations.Type"].type_checking
    assert imports["nested_type"].type_checking
    assert imports["typed_attribute"].type_checking
    assert not imports["runtime"].type_checking
    assert not imports["ordinary_guard"].type_checking
    assert snapshot.summary.class_count == 2
    assert snapshot.summary.async_function_count == 2
    assert snapshot.summary.import_statement_count == 10
    assert b"secret-decorator-argument" not in canonical_snapshot(snapshot)


@pytest.mark.parametrize(
    "path,roots,expected",
    [
        ("src/example/service.py", (), "src.example.service"),
        ("src/example/__init__.py", (), "src.example"),
        ("src/example/service.py", ("src",), "example.service"),
        ("namespace/nested/module.py", (), "namespace.nested.module"),
        ("__init__.py", (), None),
        ("bad-name/module.py", (), None),
        ("class/module.py", (), None),
        ("café.py", (), "café"),
        ("src/deep/a.py", ("src", "src/deep"), "a"),
    ],
)
def test_module_derivation(path: str, roots: tuple[str, ...], expected: str | None) -> None:
    assert module_name(path, AnalysisOptions(source_roots=roots)) == expected


def test_default_and_custom_exclusions(tmp_path: Path) -> None:
    for directory in AnalysisOptions().excluded_dirs:
        write(tmp_path, directory + "/ignored.py")
    write(tmp_path, "experiments/results/ignored.py")
    write(tmp_path, "keep.py")
    write(tmp_path, "omit.py")
    write(tmp_path, ".hidden.py")
    write(tmp_path, ".hidden/nested.py")
    write(tmp_path, "custom/ignored.py")
    options = AnalysisOptions(
        excluded_dirs=AnalysisOptions().excluded_dirs + ("custom",),
        excluded_patterns=AnalysisOptions().excluded_patterns + ("omit.py",),
    )
    snapshot = LocalRepositoryAnalyzer().analyze(tmp_path, options)
    assert [f.path for f in snapshot.files] == ["keep.py"]
    hidden = LocalRepositoryAnalyzer().analyze(tmp_path, replace(options, include_hidden=True))
    assert [f.path for f in hidden.files] == [".hidden.py", ".hidden/nested.py", "keep.py"]


def test_conflicts_and_invalid_names(tmp_path: Path) -> None:
    for path in ["src/pkg/a.py", "lib/pkg/a.py", "bad-name/a.py", "same.py", "same/__init__.py"]:
        write(tmp_path, path)
    snapshot = LocalRepositoryAnalyzer().analyze(
        tmp_path, AnalysisOptions(source_roots=("src", "lib"))
    )
    assert sum(d.code == DiagnosticCode.MODULE_CONFLICT for d in snapshot.diagnostics) == 4
    assert sum(d.code == DiagnosticCode.INVALID_MODULE for d in snapshot.diagnostics) == 1


def test_decoding_and_syntax_errors(tmp_path: Path) -> None:
    write(tmp_path, "latin.py", b"# coding: latin-1\nname = 'caf\xe9'\n")
    write(tmp_path, "invalid.py", b"# coding: invalid-secret-codec\n")
    write(tmp_path, "bytes.py", b"name='\xff'\n")
    write(tmp_path, "broken.py", b"token='do-not-disclose'; def broken(\n")
    write(tmp_path, "null.py", b"\x00")
    snapshot = LocalRepositoryAnalyzer().analyze(tmp_path, AnalysisOptions())
    assert snapshot.summary.parsed_files == 1
    assert snapshot.summary.failed_files == 4
    assert {d.code for d in snapshot.diagnostics} == {
        DiagnosticCode.SYNTAX_ERROR,
        DiagnosticCode.UNSUPPORTED_ENCODING,
    }
    assert b"do-not-disclose" not in canonical_snapshot(snapshot)
    assert b"invalid-secret-codec" not in canonical_snapshot(snapshot)
    with pytest.raises(AnalysisError):
        LocalRepositoryAnalyzer().analyze(tmp_path, AnalysisOptions(fail_fast=True))


def test_size_limit_and_empty(tmp_path: Path) -> None:
    assert (
        LocalRepositoryAnalyzer()
        .analyze(tmp_path, AnalysisOptions())
        .summary.discovered_python_files
        == 0
    )
    write(tmp_path, "large.py", b"#" * 101)
    snapshot = LocalRepositoryAnalyzer().analyze(tmp_path, AnalysisOptions(max_file_bytes=100))
    assert snapshot.summary.skipped_files == 1
    assert snapshot.files[0].sha256 is None
    assert snapshot.diagnostics[0].code == DiagnosticCode.FILE_TOO_LARGE


def test_symlinks_and_immutability(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    write(root, "safe.py")
    external = write(tmp_path, "outside/external.py", b"secret = 'outside'\n")
    symlink(root / "link.py", external)
    symlink(root / "inside.py", root / "safe.py")
    symlink(root / "directory", external.parent)
    before = manifest(root)
    snapshot = LocalRepositoryAnalyzer().analyze(root, AnalysisOptions())
    assert manifest(root) == before
    assert snapshot.summary.parsed_files == 1
    assert snapshot.summary.skipped_files == 2
    assert len(snapshot.diagnostics) == 3
    assert b"outside" not in canonical_snapshot(snapshot)
    with pytest.raises(UnsafePathError):
        LocalRepositoryAnalyzer().analyze(root, AnalysisOptions(symlink_policy="reject"))
    symlink(tmp_path / "root-link", root)
    with pytest.raises(UnsafePathError):
        LocalRepositoryAnalyzer().analyze(tmp_path / "root-link", AnalysisOptions())


def test_never_executes(tmp_path: Path, repository_root: Path) -> None:
    write(
        tmp_path,
        "malicious.py",
        (repository_root / "tests/fixtures/repositories/malicious.py.txt").read_bytes(),
    )
    before = manifest(tmp_path)
    with (
        patch("subprocess.run", side_effect=AssertionError("subprocess invoked")),
        patch("builtins.eval", side_effect=AssertionError("evaluation invoked")),
    ):
        snapshot = LocalRepositoryAnalyzer().analyze(tmp_path, AnalysisOptions())
    assert snapshot.summary.parsed_files == 1
    assert manifest(tmp_path) == before
    assert not (tmp_path / "executed-marker").exists()
    assert b"secret-source-token" not in canonical_snapshot(snapshot)


def test_determinism_locations_options_and_content(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "other-location"
    write(first, "z.py")
    write(first, "a.py")
    shutil.copytree(first, second)
    analyzer = LocalRepositoryAnalyzer()
    options = AnalysisOptions()
    snapshot = analyzer.analyze(first, options)
    assert snapshot == analyzer.analyze(first, options) == analyzer.analyze(second, options)
    assert canonical_snapshot(snapshot) == canonical_snapshot(analyzer.analyze(second, options))
    assert fingerprint(options, tuple(reversed(snapshot.files))) == snapshot.repository_fingerprint
    write(first, ".git/ignored.py", b"anything")
    assert snapshot == analyzer.analyze(first, options)
    assert (
        analyzer.analyze(first, replace(options, include_hidden=True)).repository_fingerprint
        != snapshot.repository_fingerprint
    )
    write(first, "a.py", b"value = 2\n")
    assert (
        analyzer.analyze(first, options).repository_fingerprint != snapshot.repository_fingerprint
    )
    (second / "a.py").rename(second / "b.py")
    assert (
        analyzer.analyze(second, options).repository_fingerprint != snapshot.repository_fingerprint
    )


@pytest.mark.parametrize(
    "raw,lines", [(b"", 0), (b"a", 1), (b"a\n", 1), (b"a\r\nb\r\n", 2), (b"a\rb", 2)]
)
def test_physical_lines(raw: bytes, lines: int) -> None:
    assert physical_lines(raw) == lines


def test_line_endings(tmp_path: Path) -> None:
    path = write(tmp_path, "a.py", b"x=1\ny=2\n")
    first = LocalRepositoryAnalyzer().analyze(tmp_path, AnalysisOptions())
    path.write_bytes(b"x=1\r\ny=2\r\n")
    second = LocalRepositoryAnalyzer().analyze(tmp_path, AnalysisOptions())
    assert first.summary.total_lines == second.summary.total_lines == 2
    assert first.repository_fingerprint != second.repository_fingerprint
    assert first.files[0].sha256 != second.files[0].sha256


def test_invalid_root(tmp_path: Path) -> None:
    file = write(tmp_path, "file.py")
    for root in [tmp_path / "missing", file]:
        with pytest.raises(ValueError):
            LocalRepositoryAnalyzer().analyze(root, AnalysisOptions())


def test_unreadable_file(tmp_path: Path) -> None:
    write(tmp_path, "a.py")
    real_open = os.open

    def denied(path: str, flags: int, mode: int = 0o777, *, dir_fd: int | None = None) -> int:
        if path == "a.py":
            raise PermissionError("sensitive-host-path")
        return real_open(path, flags, mode, dir_fd=dir_fd)

    with (
        patch("archguard.infrastructure.repository_analyzer.os.open", side_effect=denied),
        patch("archguard.infrastructure.repository_analyzer.os.supports_dir_fd", {os.open}),
    ):
        snapshot = LocalRepositoryAnalyzer().analyze(tmp_path, AnalysisOptions())
    assert snapshot.summary.failed_files == 1
    assert snapshot.diagnostics[0].code == DiagnosticCode.UNREADABLE_FILE
    assert b"sensitive-host-path" not in canonical_snapshot(snapshot)


def test_path_policy_and_special_files(tmp_path: Path) -> None:
    write(tmp_path, "bad\nname.py")
    write(tmp_path, "bad\ndirectory/child.py")
    write(tmp_path, "readme.txt")
    if hasattr(os, "mkfifo"):
        os.mkfifo(tmp_path / "pipe.py")
    snapshot = LocalRepositoryAnalyzer().analyze(tmp_path, AnalysisOptions())
    assert all(d.code == DiagnosticCode.PATH_POLICY_REJECTION for d in snapshot.diagnostics)
    assert all("\n" not in (d.path or "") for d in snapshot.diagnostics)


def test_platform_and_walk_errors(tmp_path: Path) -> None:
    with patch("archguard.infrastructure.repository_analyzer.os.supports_dir_fd", set()):
        with pytest.raises(UnsafePathError):
            LocalRepositoryAnalyzer().analyze(tmp_path, AnalysisOptions())
    with patch("archguard.infrastructure.repository_analyzer.os.fwalk", side_effect=OSError):
        with pytest.raises(AnalysisError):
            LocalRepositoryAnalyzer().analyze(tmp_path, AnalysisOptions())


def test_source_replaced_with_outside_symlink(tmp_path: Path) -> None:
    root = tmp_path / "source"
    source = write(root, "a.py")
    outside = write(tmp_path, "outside.py", b"secret='must-not-read'\n")
    real_open = os.open

    def replace_before_open(
        path: str, flags: int, mode: int = 0o777, *, dir_fd: int | None = None
    ) -> int:
        if path == "a.py":
            source.unlink()
            symlink(source, outside)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    with (
        patch(
            "archguard.infrastructure.repository_analyzer.os.open", side_effect=replace_before_open
        ),
        patch("archguard.infrastructure.repository_analyzer.os.supports_dir_fd", {os.open}),
    ):
        snapshot = LocalRepositoryAnalyzer().analyze(root, AnalysisOptions())
    assert snapshot.summary.failed_files == 1
    assert snapshot.files[0].sha256 is None
    assert snapshot.diagnostics[0].code == DiagnosticCode.PATH_POLICY_REJECTION


def test_growth_after_size_check(tmp_path: Path) -> None:
    source = write(tmp_path, "a.py", b"x=1\n")
    real_open = os.open

    def grow_before_open(
        path: str, flags: int, mode: int = 0o777, *, dir_fd: int | None = None
    ) -> int:
        if path == "a.py":
            source.write_bytes(b"#" * 101)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    with (
        patch("archguard.infrastructure.repository_analyzer.os.open", side_effect=grow_before_open),
        patch("archguard.infrastructure.repository_analyzer.os.supports_dir_fd", {os.open}),
    ):
        snapshot = LocalRepositoryAnalyzer().analyze(tmp_path, AnalysisOptions(max_file_bytes=100))
    assert snapshot.summary.skipped_files == 1
    assert snapshot.diagnostics[0].code == DiagnosticCode.FILE_TOO_LARGE


def test_discovery_order_does_not_change_artifact(tmp_path: Path) -> None:
    from collections.abc import Callable, Iterator

    write(tmp_path, "z/file.py")
    write(tmp_path, "a/file.py")
    write(tmp_path, "root.py")
    analyzer = LocalRepositoryAnalyzer()
    expected = analyzer.analyze(tmp_path, AnalysisOptions())
    real_walk = os.fwalk

    def reverse_walk(
        root: Path, *, follow_symlinks: bool, onerror: Callable[[OSError], None]
    ) -> Iterator[tuple[str, list[str], list[str], int]]:
        for directory, dirs, names, descriptor in real_walk(
            root, follow_symlinks=follow_symlinks, onerror=onerror
        ):
            dirs.reverse()
            names.reverse()
            yield directory, dirs, names, descriptor

    with patch("archguard.infrastructure.repository_analyzer.os.fwalk", side_effect=reverse_walk):
        actual = analyzer.analyze(tmp_path, AnalysisOptions())
    assert canonical_snapshot(actual) == canonical_snapshot(expected)


def test_directory_enumeration_failure(tmp_path: Path) -> None:
    from collections.abc import Callable, Iterator

    def failed_walk(
        root: Path, *, follow_symlinks: bool, onerror: Callable[[OSError], None]
    ) -> Iterator[tuple[str, list[str], list[str], int]]:
        onerror(PermissionError("private host path"))
        return iter(())

    with patch("archguard.infrastructure.repository_analyzer.os.fwalk", side_effect=failed_walk):
        snapshot = LocalRepositoryAnalyzer().analyze(tmp_path, AnalysisOptions())
    assert snapshot.diagnostics[0].path is None
    assert snapshot.diagnostics[0].code == DiagnosticCode.DIRECTORY_UNREADABLE
    assert snapshot.partial


def test_source_root_equal_to_file_is_diagnosed(tmp_path: Path) -> None:
    write(tmp_path, "module.py")
    snapshot = LocalRepositoryAnalyzer().analyze(
        tmp_path, AnalysisOptions(source_roots=("module.py",))
    )
    assert snapshot.files[0].module_name is None
    assert snapshot.diagnostics[0].code == DiagnosticCode.INVALID_MODULE
