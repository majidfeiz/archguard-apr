"""Repository graph command composition and JSON presentation."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Literal

import typer

from archguard.application.services.graph import BuildRepositoryGraph, InspectRepositoryGraph
from archguard.application.services.graph_builder import DeterministicGraphBuilder
from archguard.application.services.graph_queries import QueryRepositoryGraph
from archguard.domain.graph import EdgeKind, GraphBuildOptions
from archguard.entrypoints.cli.repository import report_error
from archguard.infrastructure.graph_artifacts import LocalGraphArtifacts
from archguard.infrastructure.repository_artifacts import LocalAnalysisArtifacts

app = typer.Typer(no_args_is_help=True)


def emit(value: object) -> None:
    typer.echo(json.dumps(value, sort_keys=True))


def query(artifact: Path) -> QueryRepositoryGraph:
    try:
        return QueryRepositoryGraph(InspectRepositoryGraph(LocalGraphArtifacts()).execute(artifact))
    except (ValueError, OSError) as error:
        report_error(error)


@app.command()
def build(
    snapshot: Path,
    output: Annotated[Path, typer.Option("--output")],
    protected_root: Annotated[Path | None, typer.Option("--protected-root")] = None,
    top_level_external: bool = False,
) -> None:
    """Build a graph exclusively from a validated snapshot artifact."""
    try:
        result = BuildRepositoryGraph(
            LocalAnalysisArtifacts(), DeterministicGraphBuilder(), LocalGraphArtifacts()
        ).execute(
            snapshot,
            output,
            GraphBuildOptions("top_level" if top_level_external else "full_module"),
            protected_root,
        )
        emit(
            {
                "graph_fingerprint": result.graph.graph_fingerprint,
                "summary": asdict(result.graph.summary),
                "artifact": asdict(result.artifact),
            }
        )
    except (ValueError, OSError) as error:
        report_error(error)


@app.command()
def inspect(artifact: Path, sha256: Annotated[str | None, typer.Option("--sha256")] = None) -> None:
    try:
        graph = InspectRepositoryGraph(LocalGraphArtifacts()).execute(artifact, sha256)
        emit(
            {
                "graph_schema_version": graph.graph_schema_version,
                "graph_fingerprint": graph.graph_fingerprint,
                "snapshot_fingerprint": graph.snapshot_fingerprint,
                "summary": asdict(graph.summary),
            }
        )
    except (ValueError, OSError) as error:
        report_error(error)


@app.command()
def node(artifact: Path, identifier: str) -> None:
    try:
        emit(asdict(query(artifact).node(identifier)))
    except ValueError as error:
        report_error(error)


@app.command()
def neighbors(
    artifact: Path, identifier: str, direction: str = "outgoing", kind: EdgeKind | None = None
) -> None:
    try:
        if direction not in {"incoming", "outgoing"}:
            raise ValueError("invalid direction")
        selected: Literal["incoming", "outgoing"] = (
            "incoming" if direction == "incoming" else "outgoing"
        )
        emit(query(artifact).neighbors(identifier, selected, kind))
    except ValueError as error:
        report_error(error)


@app.command()
def dependencies(artifact: Path, identifier: str) -> None:
    try:
        emit(query(artifact).dependencies(identifier))
    except ValueError as error:
        report_error(error)


@app.command("reverse-dependencies")
def reverse_dependencies(artifact: Path, identifier: str) -> None:
    try:
        emit(query(artifact).reverse_dependencies(identifier))
    except ValueError as error:
        report_error(error)


@app.command()
def path(artifact: Path, start: str, end: str, kind: EdgeKind | None = None) -> None:
    try:
        emit(query(artifact).shortest_path(start, end, kind))
    except ValueError as error:
        report_error(error)


@app.command()
def cycles(artifact: Path, runtime_only: bool = False) -> None:
    emit([asdict(group) for group in query(artifact).cycles(runtime_only)])
