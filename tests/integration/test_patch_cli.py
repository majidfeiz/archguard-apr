import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from archguard.application.services.constraint_engine import DeterministicConstraintEvaluator
from archguard.application.services.graph_builder import DeterministicGraphBuilder
from archguard.application.services.patch_validation import ValidateCandidatePatch
from archguard.domain.architecture_profile import ArchitectureProfile
from archguard.domain.architecture_report import ArchitectureReport
from archguard.domain.graph import GraphBuildOptions, RepositoryGraph
from archguard.domain.repository import AnalysisOptions
from archguard.entrypoints.cli.app import app
from archguard.infrastructure.architecture_profiles import LocalArchitectureProfiles
from archguard.infrastructure.architecture_reports import canonical_report
from archguard.infrastructure.git_worktree import GitCandidateWorkspace, GitRepositoryState
from archguard.infrastructure.patch_artifacts import LocalPatchValidationArtifacts
from archguard.infrastructure.patch_inspector import UnifiedDiffInspector
from archguard.infrastructure.repository_analyzer import LocalRepositoryAnalyzer

runner = CliRunner()


def git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def fixture(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    repository = tmp_path / "repo"
    source = repository / "src/demo"
    source.mkdir(parents=True)
    git(repository, "init", "-b", "main")
    git(repository, "config", "user.email", "test@example.invalid")
    git(repository, "config", "user.name", "ArchGuard Test")
    (source / "__init__.py").write_text("")
    (source / "model.py").write_text("VALUE = 1\n")
    (source / "service.py").write_text("from . import model\n")
    git(repository, "add", ".")
    git(repository, "commit", "-m", "baseline")
    baseline = git(repository, "rev-parse", "HEAD")
    (source / "service.py").write_text("from . import model\nVALUE = 2\n")
    patch = tmp_path / "candidate.diff"
    patch.write_text(git(repository, "diff") + "\n")
    git(repository, "checkout", "--", "src/demo/service.py")
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        """architecture_profile_schema_version: "1"
id: smoke
name: Smoke profile
assignment: {unassigned: warn, ambiguous: error}
components:
  - id: application
    selectors: [{type: module_prefix, value: demo}]
rules:
  - id: no-cycle
    type: forbid_cycles
    components: [application]
"""
    )
    return repository, patch, profile, baseline


def test_complete_cli_is_deterministic_and_inspectable(tmp_path: Path) -> None:
    repository, patch, profile, baseline = fixture(tmp_path)
    inspect = runner.invoke(app, ["patch", "inspect", str(patch)])
    assert inspect.exit_code == 0
    assert json.loads(inspect.stdout)["acceptable"] is True
    outputs = [tmp_path / "one.json", tmp_path / "two.json"]
    for output in outputs:
        result = runner.invoke(
            app,
            [
                "patch",
                "validate",
                str(repository),
                "--patch",
                str(patch),
                "--profile",
                str(profile),
                "--baseline",
                baseline,
                "--source-root",
                "src",
                "--output",
                str(output),
            ],
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["architecture_passed"] is True
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    artifact_bytes = outputs[0].read_bytes()
    assert str(tmp_path).encode() not in artifact_bytes
    assert b"from . import model" not in artifact_bytes
    for command in (
        ["result", "inspect"],
        ["result", "delta"],
        ["result", "violations", "--state", "all"],
    ):
        result = runner.invoke(app, ["patch", *command, str(outputs[0])])
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout) is not None
    assert git(repository, "status", "--porcelain") == ""
    assert "archguard-candidate-" not in git(repository, "worktree", "list", "--porcelain")
    tampered = json.loads(outputs[0].read_bytes())
    tampered["result_fingerprint"] = "0" * 64
    outputs[0].write_text(json.dumps(tampered, sort_keys=True, separators=(",", ":")) + "\n")
    invalid = runner.invoke(app, ["patch", "result", "inspect", str(outputs[0])])
    assert invalid.exit_code == 2 and "Traceback" not in invalid.output


class RecordingEvaluator:
    def __init__(self) -> None:
        self.reports: list[bytes] = []

    def evaluate(self, graph: RepositoryGraph, profile: ArchitectureProfile) -> ArchitectureReport:
        report = DeterministicConstraintEvaluator().evaluate(graph, profile)
        self.reports.append(canonical_report(report))
        return report


def test_repeated_pipeline_report_artifacts_are_byte_identical(tmp_path: Path) -> None:
    repository, patch, profile, baseline = fixture(tmp_path)
    evaluator = RecordingEvaluator()
    service = ValidateCandidatePatch(
        UnifiedDiffInspector(),
        GitRepositoryState(),
        GitCandidateWorkspace(),
        LocalRepositoryAnalyzer(),
        DeterministicGraphBuilder(),
        LocalArchitectureProfiles(),
        evaluator,
        LocalPatchValidationArtifacts(),
    )
    before = GitRepositoryState().capture(repository)
    for index in range(2):
        service.execute(
            repository,
            patch.read_bytes(),
            profile,
            baseline,
            AnalysisOptions(source_roots=("src",)),
            GraphBuildOptions(),
            output=tmp_path / f"validation-{index}.json",
        )
    assert evaluator.reports[0] == evaluator.reports[2]
    assert evaluator.reports[1] == evaluator.reports[3]
    assert (tmp_path / "validation-0.json").read_bytes() == (
        tmp_path / "validation-1.json"
    ).read_bytes()
    assert GitRepositoryState().capture(repository) == before


def test_rejected_patch_has_stable_code_and_no_content_leak(tmp_path: Path) -> None:
    patch = tmp_path / "unsafe.diff"
    secret = "DO_NOT_PRINT_THIS_HUNK"
    patch.write_text(
        "diff --git a/../x b/../x\n--- a/../x\n+++ b/../x\n@@ -1 +1 @@\n-old\n+" + secret + "\n"
    )
    result = runner.invoke(app, ["patch", "inspect", str(patch)])
    assert result.exit_code == 3
    assert "unsafe_path" in result.stdout
    assert secret not in result.stdout


def test_introduced_cycle_fails_gate_and_filters_state(tmp_path: Path) -> None:
    repository, _, profile, baseline = fixture(tmp_path)
    model = repository / "src/demo/model.py"
    model.write_text("from . import service\nVALUE = 1\n")
    patch = tmp_path / "cycle.diff"
    patch.write_text(git(repository, "diff") + "\n")
    git(repository, "checkout", "--", "src/demo/model.py")
    output = tmp_path / "cycle-result.json"
    result = runner.invoke(
        app,
        [
            "patch",
            "validate",
            str(repository),
            "--patch",
            str(patch),
            "--profile",
            str(profile),
            "--baseline",
            baseline,
            "--source-root",
            "src",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 1 and output.is_file()
    summary = json.loads(result.stdout)
    assert summary["introduced_count"] == 1 and summary["architecture_passed"] is False
    selected = runner.invoke(
        app, ["patch", "result", "violations", str(output), "--state", "introduced"]
    )
    assert selected.exit_code == 0
    assert len(json.loads(selected.stdout)["introduced"]) == 1


def test_validation_rejection_and_application_failure_are_artifacts(tmp_path: Path) -> None:
    repository, _, profile, baseline = fixture(tmp_path)
    unsafe = tmp_path / "unsafe-validation.diff"
    secret = "NEVER_LEAK_PATCH_TEXT"
    unsafe.write_text(
        f"diff --git a/../x b/../x\n--- a/../x\n+++ b/../x\n@@ -1 +1 @@\n-old\n+{secret}\n"
    )
    rejected_output = tmp_path / "rejected.json"
    rejected = runner.invoke(
        app,
        [
            "patch",
            "validate",
            str(repository),
            "--patch",
            str(unsafe),
            "--profile",
            str(profile),
            "--baseline",
            baseline,
            "--output",
            str(rejected_output),
        ],
    )
    assert rejected.exit_code == 3 and rejected_output.is_file()
    assert secret not in rejected.output and "Traceback" not in rejected.output
    cannot_apply = tmp_path / "cannot-apply.diff"
    cannot_apply.write_text(
        "diff --git a/src/demo/model.py b/src/demo/model.py\n"
        "--- a/src/demo/model.py\n+++ b/src/demo/model.py\n"
        "@@ -1 +1 @@\n-ABSENT\n+replacement\n"
    )
    failed_output = tmp_path / "failed.json"
    failed = runner.invoke(
        app,
        [
            "patch",
            "validate",
            str(repository),
            "--patch",
            str(cannot_apply),
            "--profile",
            str(profile),
            "--baseline",
            baseline,
            "--source-root",
            "src",
            "--output",
            str(failed_output),
        ],
    )
    assert failed.exit_code == 5 and failed_output.is_file()
    assert "patch_does_not_apply" in failed.stdout and "Traceback" not in failed.output
    assert git(repository, "status", "--porcelain") == ""
    assert "archguard-candidate-" not in git(repository, "worktree", "list", "--porcelain")
