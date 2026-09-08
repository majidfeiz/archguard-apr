import dataclasses
import hashlib
from pathlib import Path

import pytest

from archguard.application.services.constraint_engine import DeterministicConstraintEvaluator
from archguard.application.services.graph_builder import DeterministicGraphBuilder
from archguard.domain.architecture_profile import (
    ArchitectureComponent,
    ArchitectureProfile,
    ForbidDependency,
    ModuleSelector,
    ProfilePolicy,
)
from archguard.domain.architecture_report import ArchitectureReport
from archguard.domain.graph import GraphBuildOptions, RepositoryGraph
from archguard.domain.patch_validation import (
    MAX_PATCH_BYTES,
    ArchitectureDelta,
    PatchDiagnosticCode,
    PatchOperationKind,
    compare_reports,
)
from archguard.domain.repository import AnalysisOptions, RepositorySnapshot
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
        (modification() + b"GIT binary patch\n", PatchDiagnosticCode.BINARY),
        (modification() + b"rename from src/a.py\n", PatchDiagnosticCode.RENAME_COPY),
        (modification() + b"old mode 120000\n", PatchDiagnosticCode.UNSAFE_MODE),
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
