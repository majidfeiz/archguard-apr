"""Source-safe CLI composition for deterministic repository context retrieval."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer

from archguard.application.services.context import (
    BuildContextBundle,
    CompileRetrievalQuery,
    EvaluateRetrieval,
    RetrieveRepositoryContext,
)
from archguard.domain.context import RetrievalPolicy
from archguard.entrypoints.cli.repository import report_error
from archguard.infrastructure.artifact_io import read_artifact
from archguard.infrastructure.context_artifacts import LocalContextArtifacts, LocalRelevanceLabels
from archguard.infrastructure.graph_artifacts import LocalGraphArtifacts
from archguard.infrastructure.repository_artifacts import LocalAnalysisArtifacts
from archguard.infrastructure.source_excerpt_reader import (
    LocalSourceExcerptReader,
    SourceIdentityError,
)

app = typer.Typer(no_args_is_help=True)
bundle_app = typer.Typer(no_args_is_help=True)
evaluation_app = typer.Typer(no_args_is_help=True)
query_app = typer.Typer(no_args_is_help=True)
app.add_typer(query_app, name="query")
app.add_typer(bundle_app, name="bundle")
app.add_typer(evaluation_app, name="evaluation")


def emit(value: object) -> None:
    typer.echo(json.dumps(value, sort_keys=True))


def bounded_text(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return read_artifact(path, None, 1024 * 1024).decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("query input is not UTF-8") from None


@query_app.command("compile")
def compile_query(
    problem: Annotated[Path, typer.Option("--problem")],
    output: Annotated[Path, typer.Option("--output")],
    error: Annotated[Path | None, typer.Option("--error")] = None,
    traceback: Annotated[Path | None, typer.Option("--traceback")] = None,
    path: Annotated[list[str] | None, typer.Option("--path")] = None,
    module: Annotated[list[str] | None, typer.Option("--module")] = None,
    node: Annotated[list[str] | None, typer.Option("--node")] = None,
    symbol: Annotated[list[str] | None, typer.Option("--symbol")] = None,
    architecture_node: Annotated[list[str] | None, typer.Option("--architecture-node")] = None,
    changed_path: Annotated[list[str] | None, typer.Option("--changed-path")] = None,
    query_id: Annotated[str, typer.Option("--query-id")] = "query",
) -> None:
    try:
        value = CompileRetrievalQuery().execute(
            query_id,
            bounded_text(problem),
            bounded_text(error),
            bounded_text(traceback),
            tuple(path or ()),
            tuple(module or ()),
            tuple(node or ()),
            tuple(symbol or ()),
            tuple(architecture_node or ()),
            tuple(changed_path or ()),
        )
        reference = LocalContextArtifacts().write_query(value, output)
        emit(
            {
                "artifact": reference.path,
                "query_fingerprint": value.query_fingerprint,
                "term_count": len(value.normalized_terms),
                "diagnostic_count": len(value.diagnostics),
            }
        )
    except (ValueError, OSError) as exc:
        report_error(exc)


@app.command()
def retrieve(
    graph: Path,
    snapshot: Annotated[Path, typer.Option("--snapshot")],
    query: Annotated[Path, typer.Option("--query")],
    output: Annotated[Path, typer.Option("--output")],
    max_depth: int = 2,
    max_files: int = 12,
    max_symbols: int = 30,
    max_excerpts: int = 30,
    max_lines: int = 500,
    max_bytes: int = 50_000,
    include_tests: bool = True,
    include_external: bool = False,
    include: Annotated[list[str] | None, typer.Option("--include")] = None,
    exclude: Annotated[list[str] | None, typer.Option("--exclude")] = None,
) -> None:
    try:
        artifacts = LocalContextArtifacts()
        value = (
            RetrieveRepositoryContext(artifacts)
            .execute(
                LocalAnalysisArtifacts().read(snapshot),
                LocalGraphArtifacts().read(graph),
                artifacts.read_query(query),
                RetrievalPolicy(
                    max_depth=max_depth,
                    max_files=max_files,
                    max_symbols=max_symbols,
                    max_excerpts=max_excerpts,
                    max_lines=max_lines,
                    max_source_bytes=max_bytes,
                    include_tests=include_tests,
                    include_external=include_external,
                    include_patterns=tuple(include or ()),
                    exclude_patterns=tuple(exclude or ()),
                ),
                output,
            )
            .manifest
        )
        emit(
            {
                "manifest_fingerprint": value.manifest_fingerprint,
                "candidate_count": len(value.candidates),
                "seed_count": len(value.seeds),
                "selected_count": value.budget.selected_excerpts,
                "budget": asdict(value.budget),
                "complete": value.complete,
                "diagnostic_codes": value.diagnostics,
                "artifact": output.name,
            }
        )
        if not value.candidates:
            raise typer.Exit(1)
        if not value.complete:
            raise typer.Exit(4)
    except typer.Exit:
        raise
    except (ValueError, OSError) as exc:
        report_error(exc)


@app.command()
def inspect(manifest: Path) -> None:
    try:
        value = LocalContextArtifacts().read_manifest(manifest)
        emit(
            {
                "manifest_fingerprint": value.manifest_fingerprint,
                "method_id": value.method_id,
                "query_fingerprint": value.query_fingerprint,
                "complete": value.complete,
                "seed_count": len(value.seeds),
                "candidate_count": len(value.candidates),
                "budget": asdict(value.budget),
                "diagnostic_codes": value.diagnostics,
            }
        )
    except (ValueError, OSError) as exc:
        report_error(exc)


@app.command()
def explain(manifest: Path, candidate_id: str) -> None:
    try:
        value = LocalContextArtifacts().read_manifest(manifest)
        candidate = next((item for item in value.candidates if item.node_id == candidate_id), None)
        if candidate is None:
            raise ValueError("unknown candidate ID")
        emit(asdict(candidate))
    except (ValueError, OSError) as exc:
        report_error(exc)


@bundle_app.command("repository")
def build_bundle(
    repository: Path,
    snapshot: Annotated[Path, typer.Option("--snapshot")],
    manifest: Annotated[Path, typer.Option("--manifest")],
    output: Annotated[Path, typer.Option("--output")],
    include_source: Annotated[bool, typer.Option("--include-source")] = False,
) -> None:
    if not include_source:
        emit({"diagnostic_code": "source_acknowledgement_required", "status": "refused"})
        raise typer.Exit(3)
    try:
        artifacts = LocalContextArtifacts()
        value = BuildContextBundle(LocalSourceExcerptReader(), artifacts).execute(
            repository,
            LocalAnalysisArtifacts().read(snapshot),
            artifacts.read_manifest(manifest),
            output,
        )
        emit(
            {
                "bundle_fingerprint": value.bundle_fingerprint,
                "excerpt_count": len(value.excerpts),
                "total_lines": value.total_lines,
                "total_bytes": value.total_bytes,
                "artifact": output.name,
                "sensitivity": value.sensitivity,
                "complete": value.complete,
            }
        )
    except SourceIdentityError:
        emit({"diagnostic_code": "source_identity_mismatch", "status": "error"})
        raise typer.Exit(6) from None
    except (ValueError, OSError) as exc:
        report_error(exc)


@bundle_app.command("inspect")
def inspect_bundle(bundle: Path) -> None:
    try:
        value = LocalContextArtifacts().read_bundle(bundle)
        emit(
            {
                "bundle_fingerprint": value.bundle_fingerprint,
                "excerpt_count": len(value.excerpts),
                "total_lines": value.total_lines,
                "total_bytes": value.total_bytes,
                "sensitivity": value.sensitivity,
                "complete": value.complete,
                "diagnostic_codes": value.diagnostics,
            }
        )
    except (ValueError, OSError) as exc:
        report_error(exc)


@app.command()
def evaluate(
    manifest: Path,
    labels: Annotated[Path, typer.Option("--labels")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    try:
        artifacts = LocalContextArtifacts()
        value = EvaluateRetrieval(artifacts).execute(
            artifacts.read_manifest(manifest), LocalRelevanceLabels().load(labels), output
        )
        emit(
            {
                "evaluation_fingerprint": value.evaluation_fingerprint,
                "complete": value.complete,
                "metrics": {m.name: m.value for m in value.metrics},
                "missing_relevant_references": value.missing_relevant_references,
                "artifact": output.name,
            }
        )
        if not value.complete:
            raise typer.Exit(4)
    except typer.Exit:
        raise
    except (ValueError, OSError) as exc:
        report_error(exc)


@evaluation_app.command("inspect")
def inspect_evaluation(evaluation: Path) -> None:
    try:
        value = LocalContextArtifacts().read_evaluation(evaluation)
        emit(
            {
                "evaluation_fingerprint": value.evaluation_fingerprint,
                "manifest_fingerprint": value.manifest_fingerprint,
                "labels_fingerprint": value.labels_fingerprint,
                "complete": value.complete,
                "metrics": {m.name: m.value for m in value.metrics},
                "missing_relevant_references": value.missing_relevant_references,
            }
        )
    except (ValueError, OSError) as exc:
        report_error(exc)
