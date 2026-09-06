"""CLI composition and deterministic JSON presentation only."""

from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Never

import typer

from archguard.application.services.architecture import (
    CompileArchitectureProfile,
    EvaluateArchitecture,
    explain_violation,
    select_violations,
)
from archguard.application.services.constraint_engine import DeterministicConstraintEvaluator
from archguard.application.services.repository import UnsafePathError
from archguard.domain.enums import Severity
from archguard.entrypoints.cli.graph import emit
from archguard.infrastructure.architecture_profiles import LocalArchitectureProfiles
from archguard.infrastructure.architecture_reports import LocalArchitectureReports
from archguard.infrastructure.graph_artifacts import LocalGraphArtifacts

app = typer.Typer(no_args_is_help=True)
profile_app = typer.Typer(no_args_is_help=True)
app.add_typer(profile_app, name="profile")


def fail(error: Exception) -> Never:
    unsafe = isinstance(error, UnsafePathError)
    emit(
        {
            "error": "artifact path policy rejected"
            if unsafe
            else "invalid architecture input or artifact"
        }
    )
    raise typer.Exit(3 if unsafe else 2)


@profile_app.command("validate")
def profile_validate(profile_yaml: Path) -> None:
    try:
        profile = LocalArchitectureProfiles().load(profile_yaml)
        emit({"profile_fingerprint": profile.profile_fingerprint, "valid": True})
    except (ValueError, OSError) as error:
        fail(error)


@profile_app.command("compile")
def profile_compile(
    profile_yaml: Path,
    output: Annotated[Path, typer.Option("--output")],
    protected_root: Annotated[Path | None, typer.Option("--protected-root")] = None,
) -> None:
    try:
        profiles = LocalArchitectureProfiles()
        result = CompileArchitectureProfile(profiles, profiles).execute(
            profile_yaml, output, protected_root
        )
        emit(
            {
                "profile_fingerprint": result.profile.profile_fingerprint,
                "artifact": asdict(result.artifact),
            }
        )
    except (ValueError, OSError) as error:
        fail(error)


@profile_app.command("inspect")
def profile_inspect(
    profile_json: Path, sha256: Annotated[str | None, typer.Option("--sha256")] = None
) -> None:
    try:
        emit(asdict(LocalArchitectureProfiles().read(profile_json, sha256)))
    except (ValueError, OSError) as error:
        fail(error)


@app.command()
def evaluate(
    graph_json: Path,
    profile: Annotated[Path, typer.Option("--profile")],
    output: Annotated[Path, typer.Option("--output")],
    allow_partial: bool = False,
    protected_root: Annotated[Path | None, typer.Option("--protected-root")] = None,
) -> None:
    try:
        result = EvaluateArchitecture(
            LocalGraphArtifacts(),
            LocalArchitectureProfiles(),
            DeterministicConstraintEvaluator(),
            LocalArchitectureReports(),
        ).execute(graph_json, profile, output, protected_root)
        emit(
            {
                "graph_fingerprint": result.report.graph_fingerprint,
                "profile_fingerprint": result.report.profile_fingerprint,
                "report_fingerprint": result.report.report_fingerprint,
                "artifact": asdict(result.artifact),
                **asdict(result.report.summary),
            }
        )
        raise typer.Exit(result.exit_code(allow_partial))
    except (ValueError, OSError) as error:
        fail(error)


@app.command()
def inspect(
    report_json: Path, sha256: Annotated[str | None, typer.Option("--sha256")] = None
) -> None:
    try:
        report = LocalArchitectureReports().read(report_json, sha256)
        emit(
            {
                "architecture_report_schema_version": report.architecture_report_schema_version,
                "graph_fingerprint": report.graph_fingerprint,
                "profile_fingerprint": report.profile_fingerprint,
                "report_fingerprint": report.report_fingerprint,
                "summary": asdict(report.summary),
                "rule_results": [asdict(r) for r in report.rule_results],
                "assignment_diagnostics": [asdict(d) for d in report.assignment_diagnostics],
            }
        )
    except (ValueError, OSError) as error:
        fail(error)


@app.command()
def violations(report_json: Path, severity: Severity | None = None) -> None:
    try:
        emit(
            [
                asdict(v)
                for v in select_violations(LocalArchitectureReports().read(report_json), severity)
            ]
        )
    except (ValueError, OSError) as error:
        fail(error)


@app.command()
def explain(report_json: Path, violation_id: str) -> None:
    try:
        emit(asdict(explain_violation(LocalArchitectureReports().read(report_json), violation_id)))
    except (ValueError, OSError) as error:
        fail(error)
