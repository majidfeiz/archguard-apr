"""CLI translation and composition only; application owns orchestration."""

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Annotated, Never

import typer

from archguard.application.services.repository import (
    AnalysisError,
    AnalyzeRepository,
    InspectRepository,
    UnsafePathError,
)
from archguard.domain.enums import Severity
from archguard.domain.repository import RepositorySnapshot
from archguard.infrastructure.config import load_settings
from archguard.infrastructure.repository_analyzer import LocalRepositoryAnalyzer
from archguard.infrastructure.repository_artifacts import LocalAnalysisArtifacts

app = typer.Typer(no_args_is_help=True)


def report_error(error: Exception) -> Never:
    if isinstance(error, UnsafePathError):
        typer.echo("Error: repository path policy rejected the request.", err=True)
        raise typer.Exit(3)
    if isinstance(error, (AnalysisError, OSError)):
        typer.echo("Error: repository analysis or artifact I/O failed.", err=True)
        raise typer.Exit(1)
    typer.echo("Error: invalid repository arguments, configuration, or snapshot.", err=True)
    raise typer.Exit(2)


def summary(snapshot: RepositorySnapshot) -> dict[str, object]:
    return {
        "status": "partial" if snapshot.partial else "complete",
        "repository_fingerprint": snapshot.repository_fingerprint,
        "summary": asdict(snapshot.summary),
    }


@app.command()
def analyze(
    path: Path,
    output: Annotated[Path | None, typer.Option("--output")] = None,
    config: Annotated[Path | None, typer.Option("--config")] = None,
    source_root: Annotated[list[str] | None, typer.Option("--source-root")] = None,
    strict: Annotated[bool, typer.Option("--strict")] = False,
) -> None:
    """Read a Python repository without executing it; optionally save canonical JSON."""
    try:
        settings = load_settings(config)
        options = settings.analysis.to_domain()
        if source_root is not None:
            options = replace(options, source_roots=tuple(source_root))
        result = AnalyzeRepository(LocalRepositoryAnalyzer(), LocalAnalysisArtifacts()).execute(
            path, options, output
        )
    except (ValueError, AnalysisError, OSError) as error:
        report_error(error)
    payload = summary(result.snapshot)
    if result.artifact is not None:
        payload["artifact"] = result.artifact.path
        payload["artifact_sha256"] = result.artifact.sha256
    typer.echo(json.dumps(payload, sort_keys=True))
    if (strict or settings.analysis.strict) and any(
        d.severity == Severity.ERROR for d in result.snapshot.diagnostics
    ):
        raise typer.Exit(1)


@app.command()
def inspect(
    artifact: Path,
    sha256: Annotated[str | None, typer.Option("--sha256")] = None,
) -> None:
    """Validate a stored snapshot and optionally its raw artifact SHA-256."""
    try:
        snapshot = InspectRepository(LocalAnalysisArtifacts()).execute(artifact, sha256)
    except (ValueError, AnalysisError, OSError) as error:
        report_error(error)
    typer.echo(json.dumps(summary(snapshot), sort_keys=True))
