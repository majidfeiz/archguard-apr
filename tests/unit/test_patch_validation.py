import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from archguard.application.services.constraint_engine import DeterministicConstraintEvaluator
from archguard.application.services.graph_builder import DeterministicGraphBuilder
from archguard.domain.architecture_profile import (
    ArchitectureComponent,
    ArchitectureProfile,
    ForbidCycles,
    ForbidDependency,
    ModuleSelector,
    ProfilePolicy,
)
from archguard.domain.architecture_report import ArchitectureReport
from archguard.domain.graph import GraphBuildOptions, RepositoryGraph
from archguard.domain.patch_validation import (
    MAX_PATCH_BYTES,
    MAX_PATCH_OPERATIONS,
    MAX_PATCH_PATH_BYTES,
    ArchitectureDelta,
    PatchDiagnosticCode,
    PatchOperationKind,
    compare_reports,
)
from archguard.domain.repository import AnalysisOptions, RepositorySnapshot
from archguard.infrastructure import patch_artifacts
from archguard.infrastructure.patch_artifacts import (
    LocalPatchValidationArtifacts,
    canonical_delta,
    canonical_patch,
)
from archguard.infrastructure.patch_inspector import UnifiedDiffInspector
from archguard.infrastructure.repository_analyzer import LocalRepositoryAnalyzer


def modification(path: str = "src/a.py") -> bytes:
    return f"""diff --git a/{path} b/{path}
index 7898192..422c2b7 100644
--- a/{path}
+++ b/{path}
@@ -1 +1 @@
-old
+new
""".encode()


def codes(raw: bytes, **kwargs: object) -> set[PatchDiagnosticCode]:
    result = UnifiedDiffInspector().inspect(raw, **kwargs)  # type: ignore[arg-type]
    return {item.code for item in result.diagnostics}


def test_exact_bytes_are_fingerprinted_and_model_is_immutable() -> None:
    raw = modification()
    patch = UnifiedDiffInspector().inspect(raw)
    assert patch.acceptable
    assert patch.patch_fingerprint == hashlib.sha256(raw).hexdigest()
    assert patch.paths(PatchOperationKind.MODIFY) == ("src/a.py",)
    with pytest.raises(dataclasses.FrozenInstanceError):
        patch.byte_size = 1  # type: ignore[misc]


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (b"", PatchDiagnosticCode.EMPTY),
        (b"x\0", PatchDiagnosticCode.NUL),
        (b"not a diff\n", PatchDiagnosticCode.MALFORMED),
        (modification("../escape.py"), PatchDiagnosticCode.UNSAFE_PATH),
        (modification(".git/config"), PatchDiagnosticCode.GIT_PATH),
        (modification("bad\tname.py"), PatchDiagnosticCode.CONTROL_PATH),
        (modification("a.py") + modification("a.py"), PatchDiagnosticCode.DUPLICATE_PATH),
        (
            modification().replace(b"index ", b"GIT binary patch\nindex "),
            PatchDiagnosticCode.BINARY,
        ),
        (
            modification().replace(b"index ", b"rename from src/a.py\nindex "),
            PatchDiagnosticCode.RENAME_COPY,
        ),
        (
            modification().replace(b"index ", b"copy from src/a.py\nindex "),
            PatchDiagnosticCode.RENAME_COPY,
        ),
        (
            modification().replace(b"index ", b"old mode 120000\nindex "),
            PatchDiagnosticCode.UNSAFE_MODE,
        ),
        (
            modification().replace(b"index ", b"new file mode 160000\nindex "),
            PatchDiagnosticCode.UNSAFE_MODE,
        ),
        (
            modification().replace(b"index ", b"deleted file mode 160000\nindex "),
            PatchDiagnosticCode.UNSAFE_MODE,
        ),
        (b"x" * (MAX_PATCH_BYTES + 1), PatchDiagnosticCode.TOO_LARGE),
    ],
)
def test_rejection_policy(raw: bytes, code: PatchDiagnosticCode) -> None:
    assert code in codes(raw)


def test_add_and_delete() -> None:
    added = (
        b"diff --git a/new.py b/new.py\nnew file mode 100644\n"
        b"--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+x=1\n"
    )
    deleted = (
        b"diff --git a/old.py b/old.py\ndeleted file mode 100644\n"
        b"--- a/old.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x=1\n"
    )
    assert UnifiedDiffInspector().inspect(added).paths(PatchOperationKind.ADD) == ("new.py",)
    assert UnifiedDiffInspector().inspect(deleted).paths(PatchOperationKind.DELETE) == ("old.py",)


def test_roots_and_protection() -> None:
    assert PatchDiagnosticCode.OUTSIDE_ALLOWED_ROOT in codes(modification(), allowed_roots=("lib",))
    assert PatchDiagnosticCode.PROTECTED_PATH in codes(modification(), protected_paths=("src",))
    assert PatchDiagnosticCode.UNSAFE_PATH in codes(modification(), allowed_roots=("../src",))


def test_metadata_words_inside_hunks_are_not_misclassified() -> None:
    raw = modification().replace(b"+new", b"+GIT binary patch")
    assert UnifiedDiffInspector().inspect(raw).acceptable


@pytest.mark.parametrize(
    "raw",
    [
        modification().replace(b"@@ -1 +1 @@", b"@@ -1,2 +1 @@"),
        modification().replace(b"--- a/src/a.py", b"--- a/other.py"),
        modification().replace(b"+++ b/src/a.py", b"+++ b/other.py"),
        modification().replace(b"diff --git a/src/a.py b/src/a.py", b"diff --git /tmp/a b/a"),
    ],
)
def test_inconsistent_or_truncated_headers_are_rejected(raw: bytes) -> None:
    assert PatchDiagnosticCode.MALFORMED in codes(raw)


def test_crlf_is_not_normalized() -> None:
    lf = modification()
    crlf = lf.replace(b"\n", b"\r\n")
    assert UnifiedDiffInspector().inspect(crlf).acceptable
    assert (
        UnifiedDiffInspector().inspect(lf).patch_fingerprint
        != UnifiedDiffInspector().inspect(crlf).patch_fingerprint
    )


@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("/absolute.py", PatchDiagnosticCode.UNSAFE_PATH),
        ("C:/absolute.py", PatchDiagnosticCode.UNSAFE_PATH),
        ("dir\\file.py", PatchDiagnosticCode.UNSAFE_PATH),
        (".git", PatchDiagnosticCode.GIT_PATH),
        (".GIT/config", PatchDiagnosticCode.GIT_PATH),
        ("a" * (MAX_PATCH_PATH_BYTES + 1), PatchDiagnosticCode.PATH_TOO_LONG),
    ],
)
def test_path_adversaries(path: str, code: PatchDiagnosticCode) -> None:
    assert code in codes(modification(path))


def test_unicode_path_is_accepted_and_operation_limit_is_exact() -> None:
    assert UnifiedDiffInspector().inspect(modification("src/سلام.py")).acceptable
    at_limit = b"".join(modification(f"src/{index}.py") for index in range(MAX_PATCH_OPERATIONS))
    over_limit = at_limit + modification("src/overflow.py")
    assert len(UnifiedDiffInspector().inspect(at_limit).operations) == MAX_PATCH_OPERATIONS
    assert PatchDiagnosticCode.TOO_MANY_OPERATIONS in codes(over_limit)


def report(
    tmp_path: Path, folder: str, source: str
) -> tuple[RepositorySnapshot, RepositoryGraph, ArchitectureReport]:
    root = tmp_path / folder
    root.mkdir()
    (root / "a.py").write_text(source)
    (root / "b.py").write_text("VALUE = 1\n")
    snapshot = LocalRepositoryAnalyzer().analyze(root, AnalysisOptions())
    graph = DeterministicGraphBuilder().build(snapshot, GraphBuildOptions())
    profile = ArchitectureProfile.create(
        "delta",
        "Delta",
        (
            ArchitectureComponent("first", (ModuleSelector("module_exact", "a"),)),
            ArchitectureComponent("second", (ModuleSelector("module_exact", "b"),)),
        ),
        (ForbidDependency(id="no-b", source="first", target="second"),),
        ProfilePolicy(),
    )
    return snapshot, graph, DeterministicConstraintEvaluator().evaluate(graph, profile)


def delta(
    before: tuple[RepositorySnapshot, RepositoryGraph, ArchitectureReport],
    after: tuple[RepositorySnapshot, RepositoryGraph, ArchitectureReport],
) -> ArchitectureDelta:
    return compare_reports(
        "a" * 40,
        "b" * 64,
        before[0].repository_fingerprint,
        after[0].repository_fingerprint,
        before[1].graph_fingerprint,
        after[1].graph_fingerprint,
        before[2],
        after[2],
    )


def test_delta_classifies_introduced_resolved_and_persisting(tmp_path: Path) -> None:
    clean = report(tmp_path, "clean", "VALUE = 1\n")
    bad = report(tmp_path, "bad", "import b\n")
    introduced = delta(clean, bad)
    resolved = delta(bad, clean)
    persisting = delta(bad, bad)
    assert len(introduced.introduced) == 1 and not introduced.architecture_passed
    assert len(resolved.resolved) == 1 and resolved.architecture_passed
    assert len(persisting.persisting) == 1 and persisting.architecture_passed


def test_line_and_occurrence_changes_remain_semantically_persisting(tmp_path: Path) -> None:
    once = report(tmp_path, "once", "import b\n")
    moved_twice = report(tmp_path, "twice", "VALUE = 1\nimport b\nimport b\n")
    changed = delta(once, moved_twice)
    assert not changed.introduced and not changed.resolved
    assert len(changed.persisting) == 1
    assert changed.persisting[0].baseline.evidence != changed.persisting[0].candidate.evidence


def cycle_report(
    tmp_path: Path, folder: str, cyclic: bool, broken: bool = False
) -> tuple[RepositorySnapshot, RepositoryGraph, ArchitectureReport]:
    root = tmp_path / folder
    root.mkdir()
    (root / "a.py").write_text("import b\n" if cyclic else ("def (\n" if broken else "VALUE = 1\n"))
    (root / "b.py").write_text("import a\n" if cyclic else "VALUE = 2\n")
    snapshot = LocalRepositoryAnalyzer().analyze(root, AnalysisOptions())
    graph = DeterministicGraphBuilder().build(snapshot, GraphBuildOptions())
    profile = ArchitectureProfile.create(
        "cycles",
        "Cycles",
        (
            ArchitectureComponent(
                "all", (ModuleSelector("module_exact", "a"), ModuleSelector("module_exact", "b"))
            ),
        ),
        (ForbidCycles(id="acyclic", components=("all",)),),
        ProfilePolicy(),
    )
    return snapshot, graph, DeterministicConstraintEvaluator().evaluate(graph, profile)


def test_cycle_introduction_resolution_and_incomplete_propagation(tmp_path: Path) -> None:
    clean = cycle_report(tmp_path, "cycle-clean", False)
    cyclic = cycle_report(tmp_path, "cyclic", True)
    broken = cycle_report(tmp_path, "broken", False, True)
    assert len(delta(clean, cyclic).introduced) == 1
    assert len(delta(cyclic, clean).resolved) == 1
    incomplete = delta(clean, broken)
    assert not incomplete.comparison_complete
    assert incomplete.incompleteness_reasons == ("candidate_incomplete",)
    assert not incomplete.architecture_passed


def test_patch_and_delta_artifacts_round_trip_strictly(tmp_path: Path) -> None:
    patch = UnifiedDiffInspector().inspect(modification())
    clean = report(tmp_path, "artifact-clean", "VALUE = 1\n")
    bad = report(tmp_path, "artifact-bad", "import b\n")
    architecture_delta = delta(clean, bad)
    artifacts = LocalPatchValidationArtifacts()
    patch_path, delta_path = tmp_path / "patch.json", tmp_path / "delta.json"
    artifacts.write_patch(patch, patch_path)
    artifacts.write_delta(architecture_delta, delta_path)
    assert artifacts.read_patch(patch_path) == patch
    assert artifacts.read_delta(delta_path) == architecture_delta
    assert canonical_patch(patch).endswith(b"\n") and canonical_delta(architecture_delta).endswith(
        b"\n"
    )
    assert b"old" not in patch_path.read_bytes()
    for mutation in (b'{"x":NaN}\n', b'{"x":1,"x":2}\n', b'{"unknown":1}\n'):
        patch_path.write_bytes(mutation)
        with pytest.raises(ValueError, match="invalid patch-validation artifact"):
            artifacts.read_patch(patch_path)


def test_artifact_expected_hash_and_symlink_policy(tmp_path: Path) -> None:
    patch = UnifiedDiffInspector().inspect(modification())
    artifact = tmp_path / "patch.json"
    LocalPatchValidationArtifacts().write_patch(patch, artifact)
    expected = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert LocalPatchValidationArtifacts().read_patch(artifact, expected) == patch
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        LocalPatchValidationArtifacts().read_patch(artifact, "0" * 64)
    link = tmp_path / "link.json"
    link.symlink_to(artifact)
    with pytest.raises(ValueError):
        LocalPatchValidationArtifacts().read_patch(link)


def test_metadata_fingerprint_and_artifact_size_are_verified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch = UnifiedDiffInspector().inspect(modification())
    artifact = tmp_path / "patch.json"
    LocalPatchValidationArtifacts().write_patch(patch, artifact)
    data = json.loads(artifact.read_bytes())
    data["byte_size"] += 1
    artifact.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(ValueError, match="invalid patch-validation artifact"):
        LocalPatchValidationArtifacts().read_patch(artifact)
    monkeypatch.setattr(patch_artifacts, "MAX_PATCH_ARTIFACT_BYTES", 1)
    with pytest.raises(ValueError, match="exceeds byte limit"):
        LocalPatchValidationArtifacts().write_patch(patch, artifact)
