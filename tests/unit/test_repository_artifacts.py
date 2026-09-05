import hashlib
import json
from dataclasses import FrozenInstanceError, asdict, replace
from pathlib import Path
from unittest.mock import patch

import pytest

from archguard.application.services.repository import (
    AnalyzeRepository,
    InspectRepository,
    UnsafePathError,
)
from archguard.domain.enums import ArtifactKind
from archguard.domain.models import ArtifactReference
from archguard.domain.repository import AnalysisOptions, RepositorySnapshot, safe_path
from archguard.infrastructure.repository_analyzer import LocalRepositoryAnalyzer
from archguard.infrastructure.repository_artifacts import LocalAnalysisArtifacts
from archguard.infrastructure.repository_codec import (
    canonical_json,
    canonical_snapshot,
    decode_snapshot,
)
from tests.unit.test_repository_analysis import manifest, symlink, write

pytestmark = pytest.mark.unit


@pytest.fixture
def snapshot(tmp_path: Path) -> RepositorySnapshot:
    root = tmp_path / "source"
    write(root, "a.py", b"class C:\n    def method(self):\n        pass\n")
    return LocalRepositoryAnalyzer().analyze(root, AnalysisOptions())


def test_atomic_roundtrip_and_target_immutability(
    tmp_path: Path, snapshot: RepositorySnapshot
) -> None:
    root = tmp_path / "source"
    before = manifest(root)
    artifacts = LocalAnalysisArtifacts()
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    use_case = AnalyzeRepository(LocalRepositoryAnalyzer(), artifacts)
    result = use_case.execute(root, output=first)
    other = use_case.execute(root, output=second)
    assert result.snapshot == other.snapshot == snapshot
    assert result.artifact is not None and other.artifact is not None
    assert (
        result.artifact.sha256
        == other.artifact.sha256
        == hashlib.sha256(first.read_bytes()).hexdigest()
    )
    assert result.artifact.kind == ArtifactKind.ANALYSIS
    assert first.read_bytes() == second.read_bytes() == canonical_snapshot(snapshot)
    assert first.read_bytes().endswith(b"\n")
    assert InspectRepository(artifacts).execute(first, result.artifact.sha256) == snapshot
    assert manifest(root) == before
    with pytest.raises(ValueError, match="mismatch"):
        artifacts.read(first, "0" * 64)
    with pytest.raises(ValueError):
        artifacts.read(first, "invalid")


def test_write_failure_cleanup(tmp_path: Path, snapshot: RepositorySnapshot) -> None:
    destination = tmp_path / "existing.json"
    destination.write_bytes(b"original")
    before = set(tmp_path.iterdir())
    with patch("archguard.infrastructure.artifact_io.os.replace", side_effect=OSError):
        with pytest.raises(OSError):
            LocalAnalysisArtifacts().write(snapshot, destination)
    assert destination.read_bytes() == b"original"
    assert set(tmp_path.iterdir()) == before


def test_unsafe_output_paths(tmp_path: Path, snapshot: RepositorySnapshot) -> None:
    root = tmp_path / "source"
    artifact = LocalAnalysisArtifacts()
    for path in [
        root / "out.json",
        root / ".git" / "out.json",
        tmp_path / ".." / "out.json",
        tmp_path / "missing" / "out.json",
        root,
    ]:
        with pytest.raises(UnsafePathError):
            artifact.validate_destination(root, path)
    target = tmp_path / "target.json"
    target.touch()
    symlink(tmp_path / "link.json", target)
    with pytest.raises(UnsafePathError):
        artifact.write(snapshot, tmp_path / "link.json")
    with pytest.raises(UnsafePathError):
        artifact.read(tmp_path / "link.json")
    symlink(tmp_path / "alias", root)
    with pytest.raises(UnsafePathError):
        artifact.validate_destination(root, tmp_path / "alias" / "out.json")


def test_snapshot_immutable(snapshot: RepositorySnapshot) -> None:
    with pytest.raises(FrozenInstanceError):
        snapshot.root_label = "other"  # type: ignore[misc]  # Verify frozen runtime guard.


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": "2"},
        {"root_label": "/absolute/host"},
        {"repository_fingerprint": "bad"},
        {"language": "javascript"},
    ],
)
def test_snapshot_rejects_invalid(snapshot: RepositorySnapshot, changes: dict[str, str]) -> None:
    data = asdict(snapshot)
    data.update(changes)
    with pytest.raises(ValueError):
        decode_snapshot(canonical_json(data))


@pytest.mark.parametrize(
    "field,value",
    [
        ("byte_size", -1),
        ("line_count", -1),
        ("sha256", "bad"),
        ("path", "../a.py"),
        ("path", "/tmp/a.py"),
        ("path", "a.txt"),
        ("module_name", "invalid-name"),
        ("package_initializer", True),
        ("parse_status", "unknown"),
        ("sha256", None),
    ],
)
def test_file_invariants(snapshot: RepositorySnapshot, field: str, value: object) -> None:
    data = json.loads(canonical_snapshot(snapshot))
    data["files"][0][field] = value
    with pytest.raises(ValueError):
        decode_snapshot(canonical_json(data))


@pytest.mark.parametrize(
    "field,value",
    [
        ("identifier", "symbol:bad"),
        ("qualified_name", "not-valid"),
        ("start_line", 0),
        ("end_line", 0),
        ("parent_qualified_name", "missing"),
        ("visibility", "private"),
        ("decorators", ["x(secret)"]),
        ("method", "instance"),
    ],
)
def test_symbol_invariants(snapshot: RepositorySnapshot, field: str, value: object) -> None:
    data = json.loads(canonical_snapshot(snapshot))
    data["files"][0]["symbols"][0][field] = value
    with pytest.raises(ValueError):
        decode_snapshot(canonical_json(data))


def test_summary_unknown_fields_and_hash(snapshot: RepositorySnapshot) -> None:
    for field, value in [("summary", {}), ("unknown", 1), ("repository_fingerprint", "0" * 64)]:
        data = json.loads(canonical_snapshot(snapshot))
        data[field] = value
        with pytest.raises(ValueError):
            decode_snapshot(canonical_json(data))
    data = json.loads(canonical_snapshot(snapshot))
    data["files"][0]["unexpected"] = 42
    with pytest.raises(ValueError):
        decode_snapshot(canonical_json(data))
    with pytest.raises(ValueError):
        replace(snapshot, summary=replace(snapshot.summary, class_count=0))
    with pytest.raises(ValueError):
        replace(snapshot, files=snapshot.files + snapshot.files)


@pytest.mark.parametrize(
    "raw", [b"{", b"null", b"[]", b'{"schema_version":"1","schema_version":"1"}', b'{"a":NaN}']
)
def test_invalid_json(raw: bytes) -> None:
    with pytest.raises(ValueError):
        decode_snapshot(raw)


@pytest.mark.parametrize("path", ["a/./b.py", "../a", "/a", "a\x00b", "a\nb", "a\udcffb"])
def test_normalized_path_invariants(path: str) -> None:
    with pytest.raises(ValueError):
        safe_path(path)


@pytest.mark.parametrize(
    "option,value",
    [
        ("max_file_bytes", 0),
        ("symlink_policy", "follow"),
        ("excluded_dirs", ("a/b",)),
        ("source_roots", ("../src",)),
        ("excluded_patterns", ("/tmp/*",)),
    ],
)
def test_options_invalid(option: str, value: object) -> None:
    data = asdict(AnalysisOptions())
    data[option] = value
    from archguard.infrastructure.config import AnalysisSettings

    with pytest.raises(ValueError):
        AnalysisSettings.model_validate(data)


def test_artifact_digest_validation() -> None:
    with pytest.raises(ValueError):
        ArtifactReference("a.json", ArtifactKind.ANALYSIS, "bad")


def test_read_limit(tmp_path: Path) -> None:
    path = write(tmp_path, "large.json", b"123456")
    with patch("archguard.infrastructure.repository_artifacts.MAX_ARTIFACT_BYTES", 5):
        with pytest.raises(ValueError, match="size limit"):
            LocalAnalysisArtifacts().read(path)


def test_diagnostic_invariants(tmp_path: Path) -> None:
    root = tmp_path / "source"
    write(root, "a.py", b"def bad(\n")
    write(root, "b.py", b"def bad(\n")
    snapshot = LocalRepositoryAnalyzer().analyze(root, AnalysisOptions())
    with pytest.raises(ValueError, match="ordered"):
        replace(snapshot, diagnostics=tuple(reversed(snapshot.diagnostics)))
    data = json.loads(canonical_snapshot(snapshot))
    data["diagnostics"] = []
    data["summary"]["diagnostic_count"] = 0
    with pytest.raises(ValueError):
        decode_snapshot(canonical_json(data))
    data = json.loads(canonical_snapshot(snapshot))
    data["diagnostics"][0]["message"] = "secret-source-line"
    with pytest.raises(ValueError):
        decode_snapshot(canonical_json(data))


def test_no_host_or_source_fields(snapshot: RepositorySnapshot, tmp_path: Path) -> None:
    raw = canonical_snapshot(snapshot)
    assert str(tmp_path).encode() not in raw
    assert b"class C:" not in raw
    forbidden = {
        "hostname",
        "username",
        "cwd",
        "environment",
        "generated_at",
        "created_at",
        "contents",
        "source",
    }

    def inspect_value(value: object) -> None:
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            for item in value.values():
                inspect_value(item)
        elif isinstance(value, list):
            for item in value:
                inspect_value(item)
        elif isinstance(value, str):
            assert not value.startswith("/")

    inspect_value(json.loads(raw))


def test_use_case_requires_safe_destination_before_analysis(tmp_path: Path) -> None:
    from unittest.mock import Mock

    analyzer = Mock(spec=LocalRepositoryAnalyzer)
    writer = Mock(spec=LocalAnalysisArtifacts)
    writer.validate_destination.side_effect = UnsafePathError("unsafe")
    with pytest.raises(UnsafePathError):
        AnalyzeRepository(analyzer, writer).execute(tmp_path, output=tmp_path / "inside.json")
    analyzer.analyze.assert_not_called()
    writer.write.assert_not_called()


def test_nonregular_artifact_and_invalid_destination(
    tmp_path: Path, snapshot: RepositorySnapshot
) -> None:
    import os

    if hasattr(os, "mkfifo"):
        os.mkfifo(tmp_path / "pipe.json")
        with pytest.raises(UnsafePathError):
            LocalAnalysisArtifacts().read(tmp_path / "pipe.json")
    with pytest.raises(UnsafePathError):
        LocalAnalysisArtifacts().write(snapshot, tmp_path / "bad\nname.json")
