"""CLI composition for trusted plans and Docker-only candidate comparison."""

from dataclasses import asdict, replace
from pathlib import Path
from typing import Annotated, Literal, Never

import typer

from archguard.application.services.constraint_engine import DeterministicConstraintEvaluator
from archguard.application.services.execution import CompareFunctionalBehavior
from archguard.application.services.graph_builder import DeterministicGraphBuilder
from archguard.application.services.patch_validation import ValidateCandidatePatch
from archguard.domain.execution import (
    CANDIDATE_VALIDATION_SCHEMA,
    CandidateValidationReport,
    DeltaState,
    ExecutionEvidence,
)
from archguard.domain.patch_validation import MAX_PATCH_BYTES
from archguard.domain.repository import AnalysisOptions
from archguard.entrypoints.cli.graph import emit
from archguard.infrastructure.architecture_profiles import LocalArchitectureProfiles
from archguard.infrastructure.artifact_io import read_artifact
from archguard.infrastructure.docker_execution import DockerInfrastructureError, DockerSandbox
from archguard.infrastructure.execution_artifacts import LocalExecutionArtifacts
from archguard.infrastructure.execution_plans import LocalExecutionPlans
from archguard.infrastructure.git_worktree import (
    GitCandidateWorkspace,
    GitOperationError,
    GitRepositoryState,
)
from archguard.infrastructure.graph_artifacts import LocalGraphArtifacts
from archguard.infrastructure.patch_artifacts import LocalPatchValidationArtifacts
from archguard.infrastructure.patch_inspector import UnifiedDiffInspector
from archguard.infrastructure.repository_analyzer import LocalRepositoryAnalyzer

app = typer.Typer(no_args_is_help=True)
plan_app = typer.Typer(no_args_is_help=True)
result_app = typer.Typer(no_args_is_help=True)
app.add_typer(plan_app, name="plan")
app.add_typer(result_app, name="result")


def fail(code: int, diagnostic: str) -> Never:
    emit({"diagnostic_code": diagnostic, "status": "error"})
    raise typer.Exit(code)


@plan_app.command("validate")
def validate_plan(plan: Annotated[Path, typer.Option("--plan")]) -> None:
    """Validate a trusted plan without executing it."""
    try:
        value = LocalExecutionPlans().load(plan)
        emit(
            {
                "status": "valid",
                "plan_id": value.plan_id,
                "plan_fingerprint": value.plan_fingerprint,
            }
        )
    except (ValueError, OSError):
        fail(2, "invalid_execution_plan")


@plan_app.command("inspect")
def inspect_plan(plan: Annotated[Path, typer.Option("--plan")]) -> None:
    """Print a source-free plan summary."""
    try:
        value = LocalExecutionPlans().load(plan)
        emit(
            {
                "schema": value.schema,
                "plan_id": value.plan_id,
                "image": value.image,
                "stage_ids": [stage.stage_id for stage in value.stages],
                "plan_fingerprint": value.plan_fingerprint,
            }
        )
    except (ValueError, OSError):
        fail(2, "invalid_execution_plan")


@app.command("compare")
def compare(
    repository: Annotated[Path, typer.Option("--repo")],
    baseline: Annotated[str, typer.Option("--baseline")],
    patch: Annotated[Path, typer.Option("--patch")],
    plan: Annotated[Path, typer.Option("--plan")],
    architecture_profile: Annotated[Path, typer.Option("--architecture-profile")],
    output: Annotated[Path, typer.Option("--output")],
    source_root: Annotated[list[str] | None, typer.Option("--source-root")] = None,
    context_manifest_sha256: Annotated[
        str | None, typer.Option("--context-manifest-sha256")
    ] = None,
) -> None:
    """Validate architecture, then compare identical plans inside Docker."""
    try:
        raw = read_artifact(patch, None, MAX_PATCH_BYTES + 1)
        execution_plan = LocalExecutionPlans().load(plan)
        LocalGraphArtifacts().validate_destination(output, repository)
        states, workspaces = GitRepositoryState(), GitCandidateWorkspace()
        patch_result = ValidateCandidatePatch(
            UnifiedDiffInspector(),
            states,
            workspaces,
            LocalRepositoryAnalyzer(),
            DeterministicGraphBuilder(),
            LocalArchitectureProfiles(),
            DeterministicConstraintEvaluator(),
            LocalPatchValidationArtifacts(),
        ).execute(
            repository,
            raw,
            architecture_profile,
            baseline,
            replace(AnalysisOptions(), source_roots=tuple(source_root or ())),
        )
        if not patch_result.patch_applied:
            fail(1, "patch_rejected")
        before, after, delta = CompareFunctionalBehavior(workspaces, DockerSandbox()).execute(
            repository, patch_result.baseline_commit, raw, execution_plan, {}
        )
        report = CandidateValidationReport(
            CANDIDATE_VALIDATION_SCHEMA,
            patch_result.result_fingerprint,
            before.evidence_fingerprint,
            after.evidence_fingerprint,
            delta.delta_fingerprint,
            patch_result.patch_applied,
            patch_result.architecture_passed,
            delta.accepted,
            before.infrastructure_healthy and after.infrastructure_healthy,
            patch_result.patch_applied
            and patch_result.architecture_passed
            and delta.accepted
            and before.infrastructure_healthy
            and after.infrastructure_healthy,
            context_manifest_sha256,
        )
        artifacts = LocalExecutionArtifacts()
        artifacts.write(report, output)
        artifacts.write(before, output.with_name(output.stem + ".baseline.json"))
        artifacts.write(after, output.with_name(output.stem + ".candidate.json"))
        artifacts.write(delta, output.with_name(output.stem + ".delta.json"))
        emit(
            {
                "status": "accepted" if report.overall_accepted else "rejected",
                "report_fingerprint": report.report_fingerprint,
                "functional_delta_fingerprint": delta.delta_fingerprint,
                "fixed": sum(t.state == DeltaState.FIXED for t in delta.transitions),
                "regressed": sum(t.state == DeltaState.REGRESSED for t in delta.transitions),
            }
        )
        if not report.infrastructure_healthy:
            raise typer.Exit(3)
        if not before.completed or not after.completed:
            raise typer.Exit(4)
        raise typer.Exit(0 if report.overall_accepted else 1)
    except typer.Exit:
        raise
    except (DockerInfrastructureError, GitOperationError):
        fail(3, "sandbox_infrastructure_failure")
    except (ValueError, OSError):
        fail(2, "invalid_execution_input")


@result_app.command("inspect")
def inspect_result(result: Annotated[Path, typer.Option("--result")]) -> None:
    try:
        value = LocalExecutionArtifacts().read(result, CandidateValidationReport)
        emit(asdict(value))
    except (ValueError, OSError):
        fail(2, "invalid_execution_result")


@result_app.command("tests")
def result_tests(
    result: Annotated[Path, typer.Option("--result")],
    state: Annotated[
        Literal[
            "fixed",
            "regressed",
            "persistent_failure",
            "passed_both",
            "candidate_only",
            "baseline_only",
            "status_changed",
        ],
        typer.Option("--state"),
    ],
) -> None:
    try:
        from archguard.domain.execution import FunctionalDelta

        value = LocalExecutionArtifacts().read(result, FunctionalDelta)
        emit(
            {
                "state": state,
                "tests": [item.test_id for item in value.transitions if item.state.value == state],
            }
        )
    except (ValueError, OSError):
        fail(2, "invalid_functional_delta")


@result_app.command("evidence")
def inspect_evidence(result: Annotated[Path, typer.Option("--result")]) -> None:
    try:
        value = LocalExecutionArtifacts().read(result, ExecutionEvidence)
        emit(asdict(value))
    except (ValueError, OSError):
        fail(2, "invalid_execution_evidence")
