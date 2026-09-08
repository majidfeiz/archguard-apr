"""Thin CLI composition for safe candidate patch inspection and validation."""

from dataclasses import asdict, replace
from pathlib import Path
from typing import Annotated, Literal, Never

import typer

from archguard.application.services.constraint_engine import DeterministicConstraintEvaluator
from archguard.application.services.graph_builder import DeterministicGraphBuilder
from archguard.application.services.patch_validation import ValidateCandidatePatch
from archguard.domain.patch_validation import (
    MAX_PATCH_BYTES,
    CandidatePatch,
    PatchOperationKind,
    PatchValidationResult,
)
from archguard.domain.repository import AnalysisOptions
from archguard.entrypoints.cli.graph import emit
from archguard.infrastructure.architecture_profiles import LocalArchitectureProfiles
from archguard.infrastructure.artifact_io import read_artifact
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
result_app = typer.Typer(no_args_is_help=True)
app.add_typer(result_app, name="result")


def fail(code: int, diagnostic: str) -> Never:
    emit({"diagnostic_code": diagnostic, "status": "error"})
    raise typer.Exit(code)


def patch_summary(patch: CandidatePatch) -> dict[str, object]:
    return {
        "candidate_patch_schema_version": patch.candidate_patch_schema_version,
        "patch_fingerprint": patch.patch_fingerprint,
        "byte_size": patch.byte_size,
        "operation_count": len(patch.operations),
        "changed_paths": patch.changed_paths,
        "added_paths": patch.paths(PatchOperationKind.ADD),
        "modified_paths": patch.paths(PatchOperationKind.MODIFY),
        "deleted_paths": patch.paths(PatchOperationKind.DELETE),
        "binary_patch_present": patch.binary_patch_present,
        "acceptable": patch.acceptable,
        "diagnostics": [asdict(item) for item in patch.diagnostics],
    }


def result_summary(result: PatchValidationResult) -> dict[str, object]:
    delta = result.delta
    return {
        "patch_validation_schema_version": result.patch_validation_schema_version,
        "status": result.status,
        "baseline_commit": result.baseline_commit,
        "patch_fingerprint": result.patch.patch_fingerprint,
        "patch_applied": result.patch_applied,
        "comparison_complete": result.comparison_complete,
        "architecture_passed": result.architecture_passed,
        "validation_completed": result.validation_completed,
        "diagnostic_codes": result.diagnostic_codes,
        "introduced_count": len(delta.introduced) if delta else 0,
        "resolved_count": len(delta.resolved) if delta else 0,
        "persisting_count": len(delta.persisting) if delta else 0,
        "result_fingerprint": result.result_fingerprint,
    }


@app.command()
def inspect(
    patch_file: Path,
    allowed_root: Annotated[list[str] | None, typer.Option("--allowed-root")] = None,
    protected_path: Annotated[list[str] | None, typer.Option("--protected-path")] = None,
) -> None:
    """Inspect exact patch bytes without displaying patch contents."""
    try:
        raw = read_artifact(patch_file, None, MAX_PATCH_BYTES + 1)
        patch = UnifiedDiffInspector().inspect(
            raw, tuple(allowed_root or ()), tuple(protected_path or ())
        )
        emit(patch_summary(patch))
        if not patch.acceptable:
            raise typer.Exit(3)
    except typer.Exit:
        raise
    except (ValueError, OSError):
        fail(2, "patch_unreadable")


@app.command()
def validate(
    repository: Path,
    patch: Annotated[Path, typer.Option("--patch")],
    profile: Annotated[Path, typer.Option("--profile")],
    baseline: Annotated[str, typer.Option("--baseline")],
    output: Annotated[Path, typer.Option("--output")],
    source_root: Annotated[list[str] | None, typer.Option("--source-root")] = None,
    allowed_root: Annotated[list[str] | None, typer.Option("--allowed-root")] = None,
    protected_path: Annotated[list[str] | None, typer.Option("--protected-path")] = None,
) -> None:
    """Apply only in an isolated detached worktree and compare architecture."""
    try:
        raw = read_artifact(patch, None, MAX_PATCH_BYTES + 1)
        LocalGraphArtifacts().validate_destination(output, repository)
        options = replace(AnalysisOptions(), source_roots=tuple(source_root or ()))
        result = ValidateCandidatePatch(
            UnifiedDiffInspector(),
            GitRepositoryState(),
            GitCandidateWorkspace(),
            LocalRepositoryAnalyzer(),
            DeterministicGraphBuilder(),
            LocalArchitectureProfiles(),
            DeterministicConstraintEvaluator(),
        ).execute(
            repository,
            raw,
            profile,
            baseline,
            options,
            allowed_roots=tuple(allowed_root or ()),
            protected_paths=tuple(protected_path or ()),
        )
        LocalPatchValidationArtifacts().write(result, output)
        emit(result_summary(result))
        raise typer.Exit(result.exit_code)
    except typer.Exit:
        raise
    except GitOperationError:
        fail(5, "isolated_git_failure")
    except (ValueError, OSError):
        fail(2, "invalid_patch_validation_input")


@result_app.command("inspect")
def inspect_result(
    artifact: Path, sha256: Annotated[str | None, typer.Option("--sha256")] = None
) -> None:
    try:
        emit(result_summary(LocalPatchValidationArtifacts().read(artifact, sha256)))
    except (ValueError, OSError):
        fail(2, "invalid_validation_artifact")


@result_app.command("delta")
def show_delta(artifact: Path) -> None:
    try:
        value = LocalPatchValidationArtifacts().read(artifact)
        if value.delta is None:
            fail(4, "comparison_incomplete")
        emit(asdict(value.delta))
    except (ValueError, OSError):
        fail(2, "invalid_validation_artifact")


@result_app.command("violations")
def violations(
    artifact: Path, state: Literal["introduced", "resolved", "persisting", "all"] = "all"
) -> None:
    try:
        value = LocalPatchValidationArtifacts().read(artifact)
        if value.delta is None:
            fail(4, "comparison_incomplete")
        delta = value.delta
        payload: dict[str, object] = {}
        if state in {"introduced", "all"}:
            payload["introduced"] = [asdict(item) for item in delta.introduced]
        if state in {"resolved", "all"}:
            payload["resolved"] = [asdict(item) for item in delta.resolved]
        if state in {"persisting", "all"}:
            payload["persisting"] = [asdict(item) for item in delta.persisting]
        emit(payload)
    except (ValueError, OSError):
        fail(2, "invalid_validation_artifact")
