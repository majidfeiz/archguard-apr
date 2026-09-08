from pathlib import Path

import pytest
from typer.testing import CliRunner

from archguard.application.services.context import (
    CompileRetrievalQuery,
    RetrieveRepositoryContext,
)
from archguard.application.services.graph_builder import DeterministicGraphBuilder
from archguard.domain.context import RetrievalPolicy
from archguard.domain.graph import GraphBuildOptions
from archguard.domain.repository import AnalysisOptions
from archguard.entrypoints.cli.app import app
from archguard.infrastructure.context_artifacts import LocalContextArtifacts
from archguard.infrastructure.graph_artifacts import LocalGraphArtifacts
from archguard.infrastructure.repository_analyzer import LocalRepositoryAnalyzer
from archguard.infrastructure.repository_artifacts import LocalAnalysisArtifacts
from archguard.infrastructure.source_excerpt_reader import (
    MAX_SOURCE_LINE_BYTES,
    LocalSourceExcerptReader,
    SourceIdentityError,
)

runner = CliRunner()


def fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    repository = tmp_path / "repository"
    source = repository / "src/demo"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("")
    (source / "model.py").write_text('MESSAGE = "سلام"\n')
    (source / "repository.py").write_text(
        "from .model import MESSAGE\n\ndef load():\n    return MESSAGE\n"
    )
    (source / "service.py").write_text(
        "from .repository import load\n\ndef run():\n    return load()\n"
    )
    (source / "decoy.py").write_text("VALUE = 1\n")
    snapshot = LocalRepositoryAnalyzer().analyze(repository, AnalysisOptions(source_roots=("src",)))
    graph = DeterministicGraphBuilder().build(snapshot, GraphBuildOptions())
    snapshot_path, graph_path = tmp_path / "snapshot.json", tmp_path / "graph.json"
    LocalAnalysisArtifacts().write(snapshot, snapshot_path)
    LocalGraphArtifacts().write(graph, graph_path)
    return repository, snapshot_path, graph_path


def test_all_context_commands_are_deterministic_and_source_safe(tmp_path: Path) -> None:
    repository, snapshot, graph = fixture(tmp_path)
    secret = "SECRET_DO_NOT_ECHO"
    problem, error, traceback = (
        tmp_path / "problem.txt",
        tmp_path / "error.txt",
        tmp_path / "trace.txt",
    )
    problem.write_text("Service run fails while loading repository data")
    error.write_text(secret)
    traceback.write_text('File "src/demo/service.py", line 4, in run\n')
    queries = [tmp_path / "query-one.json", tmp_path / "query-two.json"]
    for output in queries:
        result = runner.invoke(
            app,
            [
                "context",
                "query",
                "compile",
                "--problem",
                str(problem),
                "--error",
                str(error),
                "--traceback",
                str(traceback),
                "--module",
                "demo.service",
                "--symbol",
                "run",
                "--output",
                str(output),
            ],
        )
        assert result.exit_code == 0 and secret not in result.output
    assert queries[0].read_bytes() == queries[1].read_bytes()
    manifests = [tmp_path / "manifest-one.json", tmp_path / "manifest-two.json"]
    for output in manifests:
        result = runner.invoke(
            app,
            [
                "context",
                "retrieve",
                str(graph),
                "--snapshot",
                str(snapshot),
                "--query",
                str(queries[0]),
                "--max-depth",
                "2",
                "--max-files",
                "4",
                "--max-symbols",
                "8",
                "--max-lines",
                "100",
                "--max-bytes",
                "5000",
                "--output",
                str(output),
            ],
        )
        assert result.exit_code == 0 and secret not in result.output
    assert manifests[0].read_bytes() == manifests[1].read_bytes()
    manifest = LocalContextArtifacts().read_manifest(manifests[0])
    for args in (
        ["context", "inspect", str(manifests[0])],
        ["context", "explain", str(manifests[0]), manifest.candidates[0].node_id],
    ):
        result = runner.invoke(app, args)
        assert result.exit_code == 0 and secret not in result.output
    refused = runner.invoke(
        app,
        [
            "context",
            "bundle",
            "repository",
            str(repository),
            "--snapshot",
            str(snapshot),
            "--manifest",
            str(manifests[0]),
            "--output",
            str(tmp_path / "refused.json"),
        ],
    )
    assert refused.exit_code == 3 and not (tmp_path / "refused.json").exists()
    bundles = [tmp_path / "bundle-one.json", tmp_path / "bundle-two.json"]
    for output in bundles:
        built = runner.invoke(
            app,
            [
                "context",
                "bundle",
                "repository",
                str(repository),
                "--snapshot",
                str(snapshot),
                "--manifest",
                str(manifests[0]),
                "--output",
                str(output),
                "--include-source",
            ],
        )
        assert built.exit_code == 0
        assert "return load()" not in built.output and str(repository) not in built.output
    assert bundles[0].read_bytes() == bundles[1].read_bytes()
    inspected = runner.invoke(app, ["context", "bundle", "inspect", str(bundles[0])])
    assert inspected.exit_code == 0 and "return load()" not in inspected.output
    labels = tmp_path / "labels.yaml"
    labels.write_text(
        'retrieval_labels_schema_version: "1"\nrelevant_node_ids:\n'
        f"  - {manifest.candidates[0].node_id}\n"
    )
    evaluations = [tmp_path / "eval-one.json", tmp_path / "eval-two.json"]
    for output in evaluations:
        evaluated = runner.invoke(
            app,
            [
                "context",
                "evaluate",
                str(manifests[0]),
                "--labels",
                str(labels),
                "--output",
                str(output),
            ],
        )
        assert evaluated.exit_code == 0
    assert evaluations[0].read_bytes() == evaluations[1].read_bytes()
    inspected_eval = runner.invoke(app, ["context", "evaluation", "inspect", str(evaluations[0])])
    assert inspected_eval.exit_code == 0


def test_source_reader_detects_mutation_type_symlink_delete_and_encoding(tmp_path: Path) -> None:
    repository, snapshot_path, _ = fixture(tmp_path)
    snapshot = LocalAnalysisArtifacts().read(snapshot_path)
    reader = LocalSourceExcerptReader()
    excerpt = reader.read(repository, snapshot, "src/demo/model.py", 1, 1)
    assert excerpt.content == 'MESSAGE = "سلام"\n'
    target = repository / "src/demo/model.py"
    target.write_text("changed\n")
    with pytest.raises(SourceIdentityError):
        reader.read(repository, snapshot, "src/demo/model.py", 1, 1)
    target.unlink()
    target.symlink_to(repository / "src/demo/service.py")
    with pytest.raises(SourceIdentityError):
        reader.read(repository, snapshot, "src/demo/model.py", 1, 1)
    target.unlink()
    target.mkdir()
    with pytest.raises(SourceIdentityError):
        reader.read(repository, snapshot, "src/demo/model.py", 1, 1)
    target.rmdir()
    with pytest.raises(SourceIdentityError):
        reader.read(repository, snapshot, "src/demo/model.py", 1, 1)


def test_bundle_fails_closed_on_toctou_without_source_leak(tmp_path: Path) -> None:
    repository, snapshot_path, graph_path = fixture(tmp_path)
    snapshot = LocalAnalysisArtifacts().read(snapshot_path)
    graph = LocalGraphArtifacts().read(graph_path)
    query = CompileRetrievalQuery().execute("q", "service run", paths=("src/demo/service.py",))
    artifacts = LocalContextArtifacts()
    manifest = (
        RetrieveRepositoryContext(artifacts)
        .execute(snapshot, graph, query, RetrievalPolicy(max_source_bytes=10_000))
        .manifest
    )
    manifest_path = tmp_path / "manifest.json"
    artifacts.write_manifest(manifest, manifest_path)
    secret = "MUTATED_SECRET_CONTENT"
    (repository / "src/demo/service.py").write_text(secret)
    result = runner.invoke(
        app,
        [
            "context",
            "bundle",
            "repository",
            str(repository),
            "--snapshot",
            str(snapshot_path),
            "--manifest",
            str(manifest_path),
            "--output",
            str(tmp_path / "bundle.json"),
            "--include-source",
        ],
    )
    assert result.exit_code == 6 and secret not in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b"x" * (MAX_SOURCE_LINE_BYTES + 1), "line exceeds"),
        (b"\xff\xfe\n", "not UTF-8"),
    ],
)
def test_source_reader_rejects_oversized_lines_and_invalid_encoding(
    tmp_path: Path, raw: bytes, message: str
) -> None:
    repository = tmp_path / "unsafe-source"
    source = repository / "src"
    source.mkdir(parents=True)
    (source / "unsafe.py").write_bytes(raw)
    snapshot = LocalRepositoryAnalyzer().analyze(
        repository,
        AnalysisOptions(source_roots=("src",), max_file_bytes=MAX_SOURCE_LINE_BYTES + 10),
    )
    with pytest.raises(SourceIdentityError, match=message):
        LocalSourceExcerptReader().read(repository, snapshot, "src/unsafe.py", 1, 1)
    with pytest.raises(ValueError):
        LocalSourceExcerptReader().read(repository, snapshot, "../unsafe.py", 1, 1)
