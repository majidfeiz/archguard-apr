import builtins
import hashlib
import json
import subprocess
from dataclasses import FrozenInstanceError, asdict, replace
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from archguard.application.services.graph import BuildRepositoryGraph, InspectRepositoryGraph
from archguard.application.services.graph_builder import DeterministicGraphBuilder
from archguard.application.services.graph_queries import QueryRepositoryGraph, components
from archguard.application.services.repository import UnsafePathError
from archguard.domain.graph import (
    EdgeKind,
    GraphBuildOptions,
    GraphDiagnosticCode,
    GraphEdge,
    GraphNode,
    NodeKind,
    RepositoryGraph,
    Resolution,
)
from archguard.domain.repository import AnalysisOptions, RepositorySnapshot
from archguard.entrypoints.cli.app import app
from archguard.infrastructure.graph_artifacts import (
    LocalGraphArtifacts,
    canonical_graph,
    decode_graph,
)
from archguard.infrastructure.repository_analyzer import LocalRepositoryAnalyzer
from archguard.infrastructure.repository_artifacts import LocalAnalysisArtifacts

pytestmark = pytest.mark.unit


@pytest.fixture
def snapshot(tmp_path: Path) -> RepositorySnapshot:
    files = {
        "pkg/__init__.py": "from . import a\n",
        "pkg/a.py": (
            "import pkg.b as alias\n"
            "import pkg.b\n"
            "from pkg import b\n"
            "from pkg import value\n"
            "from pkg import *\n"
            "import requests.sessions\n"
            "from . import b\n"
            "from .missing import thing\n"
            "from ... import outside\n"
            "class C:\n"
            "    def method(self):\n"
            "        async def nested(): pass\n"
            "        return nested\n"
            "def duplicate(): pass\n"
            "def duplicate(): pass\n"
        ),
        "pkg/b.py": "import pkg.a\nimport pkg.b\n",
        "ns/c.py": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import ns.d\n",
        "ns/d.py": "import ns.c\n",
        "pkg/sub/__init__.py": "from .. import a\nfrom ..a import C\n",
        "isolated.py": "pass\n",
        "bad-name.py": "import os\ndef keep(): pass\n",
        "broken.py": "def broken(:\n",
    }
    root = tmp_path / "source"
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return LocalRepositoryAnalyzer().analyze(root, AnalysisOptions())


def build(snapshot: RepositorySnapshot) -> RepositoryGraph:
    return DeterministicGraphBuilder().build(snapshot, GraphBuildOptions())


def test_graph_structure_resolution_and_queries(snapshot: RepositorySnapshot) -> None:
    graph = build(snapshot)
    query = QueryRepositoryGraph(graph)
    assert graph.summary.partial
    assert graph.summary.file_nodes == len(snapshot.files)
    assert {n.kind for n in graph.nodes} == set(NodeKind)
    assert query.node("repository:root").kind == NodeKind.REPOSITORY
    assert query.node("file:broken.py").file is not None
    assert (
        len(
            {
                n.identifier
                for n in graph.nodes
                if n.symbol and n.symbol.qualified_name == "duplicate"
            }
        )
        == 2
    )
    assert query.dependencies("module:pkg.a") == (
        "external-module:requests.sessions",
        "module:pkg",
        "module:pkg.b",
    )
    assert query.reverse_dependencies("module:pkg.a") == (
        "module:pkg",
        "module:pkg.b",
        "module:pkg.sub",
    )
    assert query.neighbors("module:pkg.a", "incoming", EdgeKind.DEFINES) == ("file:pkg/a.py",)
    assert query.shortest_path("module:pkg.a", "module:pkg.b", EdgeKind.IMPORTS) == (
        "module:pkg.a",
        "module:pkg.b",
    )
    assert query.shortest_path("module:pkg.a", "module:isolated") is None
    assert query.shortest_path("module:pkg.a", "module:pkg.a") == ("module:pkg.a",)
    imports = [e for e in graph.edges if e.kind == EdgeKind.IMPORTS]
    assert sum(e.source == "module:pkg.a" and e.target == "module:pkg.b" for e in imports) == 4
    assert any(e.import_record and e.import_record.alias == "alias" for e in imports)
    assert any(e.import_record and e.import_record.wildcard for e in imports)
    assert {d.code for d in graph.diagnostics} >= {
        GraphDiagnosticCode.INCOMPLETE_SNAPSHOT,
        GraphDiagnosticCode.INVALID_IMPORTER,
        GraphDiagnosticCode.UNRESOLVED_RELATIVE,
        GraphDiagnosticCode.BEYOND_ROOT,
    }
    assert any(
        c.type_checking_only and c.nodes == ("module:ns.c", "module:ns.d") for c in query.cycles()
    )
    assert all(not c.type_checking_only for c in query.cycles(runtime_only=True))
    assert not any("module:ns.c" in c.nodes for c in query.cycles(runtime_only=True))
    assert any(not c.cyclic and c.nodes == ("module:isolated",) for c in query.module_components())
    assert query.statistics() == graph.summary
    with pytest.raises(ValueError):
        query.node("missing")
    with pytest.raises(ValueError):
        query.dependencies("repository:root")
    with pytest.raises(ValueError):
        query.neighbors("repository:root", "invalid")  # type: ignore[arg-type]
    with pytest.raises(FrozenInstanceError):
        graph.nodes = ()  # type: ignore[misc]


def test_determinism_no_io(snapshot: RepositorySnapshot, tmp_path: Path) -> None:
    first = build(snapshot)
    with (
        patch.object(builtins, "open", side_effect=AssertionError("source read")),
        patch.object(Path, "read_bytes", side_effect=AssertionError("source read")),
        patch.object(subprocess, "run", side_effect=AssertionError("execution")),
    ):
        second = build(snapshot)
    assert first == second
    assert canonical_graph(first) == canonical_graph(second)
    assert decode_graph(canonical_graph(first)) == first
    assert str(tmp_path).encode() not in canonical_graph(first)
    assert b"return nested" not in canonical_graph(first)
    assert b"timestamp" not in canonical_graph(first)
    alternate = DeterministicGraphBuilder().build(snapshot, GraphBuildOptions("top_level"))
    assert alternate.graph_fingerprint != first.graph_fingerprint
    assert QueryRepositoryGraph(alternate).node("external-module:requests")
    with pytest.raises(ValueError):
        replace(snapshot, files=tuple(reversed(snapshot.files)))


def test_ambiguous_modules(tmp_path: Path) -> None:
    for name, source in {
        "a.py": "import a\ndef keep(): pass\n",
        "a/__init__.py": "pass\n",
        "b.py": "from a import item\n",
    }.items():
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True)
        path.write_text(source)
    graph = build(LocalRepositoryAnalyzer().analyze(tmp_path, AnalysisOptions()))
    assert "module:a" not in {n.identifier for n in graph.nodes}
    assert graph.summary.ambiguous_imports == 2
    assert graph.summary.partial
    assert any(e.source == "file:a.py" and e.target.startswith("symbol:") for e in graph.edges)
    assert decode_graph(canonical_graph(graph)) == graph


@pytest.mark.parametrize(
    "mutation",
    [
        "schema",
        "fingerprint",
        "summary",
        "node_order",
        "duplicate_node",
        "duplicate_edge",
        "node_prefix",
        "missing_file",
        "edge_target",
        "structural",
        "metadata",
        "extra",
        "nan",
        "inf",
        "duplicate_key",
    ],
)
def test_reject_untrusted_graph(snapshot: RepositorySnapshot, mutation: str) -> None:
    data = asdict(build(snapshot))
    raw = canonical_graph(build(snapshot))
    if mutation == "schema":
        data["graph_schema_version"] = "2"
    elif mutation == "fingerprint":
        data["graph_fingerprint"] = "0" * 64
    elif mutation == "summary":
        data["summary"]["total_nodes"] += 1
    elif mutation == "node_order":
        data["nodes"] = tuple(reversed(data["nodes"]))
    elif mutation == "duplicate_node":
        data["nodes"] += (data["nodes"][0],)
    elif mutation == "duplicate_edge":
        data["edges"] += (data["edges"][0],)
    elif mutation == "node_prefix":
        data["nodes"][0]["identifier"] = "file:/tmp/private"
    elif mutation == "missing_file":
        data["nodes"] = tuple(n for n in data["nodes"] if n["identifier"] != "file:pkg/a.py")
    elif mutation == "edge_target":
        data["edges"][0]["target"] = "missing"
    elif mutation == "structural":
        data["edges"] = data["edges"][1:]
    elif mutation == "metadata":
        data["nodes"][0]["source_contents"] = "secret"
    elif mutation == "extra":
        data["extra"] = True
    elif mutation == "nan":
        raw = raw.replace(b'"total_nodes":', b'"total_nodes":NaN,"unused":')
    elif mutation == "inf":
        raw = raw.replace(b'"total_nodes":', b'"total_nodes":Infinity,"unused":')
    elif mutation == "duplicate_key":
        raw = b'{"graph_schema_version":"1",' + raw[1:]
    if mutation not in {"nan", "inf", "duplicate_key"}:
        raw = json.dumps(data).encode()
    with pytest.raises(ValueError, match="invalid repository graph"):
        decode_graph(raw)


def test_persistence_and_safety(snapshot: RepositorySnapshot, tmp_path: Path) -> None:
    graph = build(snapshot)
    adapter = LocalGraphArtifacts()
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    ref = adapter.write(graph, first)
    adapter.write(graph, second)
    assert first.read_bytes() == second.read_bytes()
    assert ref.sha256 == hashlib.sha256(first.read_bytes()).hexdigest()
    assert InspectRepositoryGraph(adapter).execute(first, ref.sha256) == graph
    with pytest.raises(ValueError):
        adapter.read(first, "0" * 64)
    with patch("archguard.infrastructure.graph_artifacts.MAX_GRAPH_BYTES", 10):
        with pytest.raises(ValueError):
            adapter.read(first)
    with pytest.raises(UnsafePathError):
        adapter.validate_destination(first, tmp_path)
    with pytest.raises(UnsafePathError):
        adapter.validate_destination(first, source=first)
    link = tmp_path / "link.json"
    link.symlink_to(first)
    with pytest.raises(UnsafePathError):
        adapter.read(link)
    with pytest.raises(UnsafePathError):
        adapter.validate_destination(link)
    with patch("archguard.infrastructure.artifact_io.os.replace", side_effect=OSError):
        with pytest.raises(OSError):
            adapter.write(graph, second)
    assert not list(tmp_path.glob(".archguard-*"))
    source = tmp_path / "snapshot.json"
    LocalAnalysisArtifacts().write(snapshot, source)
    service = BuildRepositoryGraph(LocalAnalysisArtifacts(), DeterministicGraphBuilder(), adapter)
    assert service.execute(source, second).graph == graph
    with pytest.raises(ValueError):
        service.execute(source, source)


def test_cli(snapshot: RepositorySnapshot, tmp_path: Path) -> None:
    source, output = tmp_path / "snapshot.json", tmp_path / "graph.json"
    LocalAnalysisArtifacts().write(snapshot, source)
    runner = CliRunner()
    commands = [
        ["build", str(source), "--output", str(output)],
        ["inspect", str(output)],
        ["node", str(output), "module:pkg.a"],
        ["neighbors", str(output), "module:pkg.a"],
        ["neighbors", str(output), "module:pkg.a", "--direction", "incoming", "--kind", "imports"],
        ["dependencies", str(output), "module:pkg.a"],
        ["reverse-dependencies", str(output), "module:pkg.a"],
        ["path", str(output), "module:pkg.a", "module:pkg.b"],
        ["path", str(output), "module:pkg.a", "module:isolated"],
        ["cycles", str(output)],
        ["cycles", str(output), "--runtime-only"],
    ]
    for command in commands:
        result = runner.invoke(app, ["graph", *command])
        assert result.exit_code == 0, result.output
        assert str(tmp_path) not in result.output
        assert result.output == runner.invoke(app, ["graph", *command]).output
    for command in [
        ["node", str(output), "missing"],
        ["neighbors", str(output), "missing"],
        ["neighbors", str(output), "module:pkg.a", "--direction", "invalid"],
        ["dependencies", str(output), "missing"],
        ["reverse-dependencies", str(output), "missing"],
        ["path", str(output), "missing", "module:pkg.a"],
    ]:
        assert runner.invoke(app, ["graph", *command]).exit_code == 2
    output.write_text("bad json")
    assert runner.invoke(app, ["graph", "inspect", str(output)]).exit_code == 2
    assert runner.invoke(app, ["graph", "cycles", str(output)]).exit_code == 2
    source.write_text("bad json")
    assert (
        runner.invoke(app, ["graph", "build", str(source), "--output", str(output)]).exit_code == 2
    )


def test_scc_long_chain_and_self_loop() -> None:
    adjacency = {str(i): {str(i + 1)} for i in range(3000)}
    adjacency["3000"] = set()
    assert len(components(adjacency)) == 3001
    assert components({"a": {"a"}, "b": set()}) == (("a",), ("b",))


def test_invalid_domain_metadata() -> None:
    with pytest.raises(ValueError):
        GraphNode("repository:other", NodeKind.REPOSITORY)
    with pytest.raises(ValueError):
        GraphBuildOptions("invalid")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        GraphEdge.create(EdgeKind.IMPORTS, "a", "b")
    with pytest.raises(ValueError):
        GraphEdge.create(EdgeKind.CONTAINS, "a", "b", resolution=Resolution.INTERNAL)


def test_lexical_paths_self_cycle_and_checkout_identity(tmp_path: Path) -> None:
    contents = {
        "a.py": "import c\nimport b\n",
        "b.py": "import d\n",
        "c.py": "import d\n",
        "d.py": "import d\n",
    }
    graphs = []
    for directory in ("checkout-one", "checkout-two"):
        root = tmp_path / directory
        root.mkdir()
        for name, content in contents.items():
            (root / name).write_text(content)
        graphs.append(build(LocalRepositoryAnalyzer().analyze(root, AnalysisOptions())))
    assert canonical_graph(graphs[0]) == canonical_graph(graphs[1])
    query = QueryRepositoryGraph(graphs[0])
    assert query.shortest_path("module:a", "module:d") == ("module:a", "module:b", "module:d")
    assert [(c.nodes, c.type_checking_only) for c in query.cycles()] == [(("module:d",), False)]
    (tmp_path / "checkout-two/d.py").write_text("pass\n")
    changed = build(LocalRepositoryAnalyzer().analyze(tmp_path / "checkout-two", AnalysisOptions()))
    assert changed.graph_fingerprint != graphs[0].graph_fingerprint


def test_recomputed_invalid_reference(snapshot: RepositorySnapshot) -> None:
    graph = build(snapshot)
    edge = next(e for e in graph.edges if e.kind == EdgeKind.IMPORTS)
    dangling = GraphEdge.create(
        edge.kind,
        edge.source,
        "external-module:missing",
        edge.import_record,
        edge.resolution,
        edge.occurrence,
    )
    with pytest.raises(ValueError):
        RepositoryGraph.create(
            graph.snapshot_fingerprint,
            graph.build_options,
            graph.nodes,
            tuple(
                sorted(
                    (dangling if e == edge else e for e in graph.edges), key=lambda e: e.identifier
                )
            ),
            graph.diagnostics,
            graph.input_partial,
        )


def test_empty_snapshot(tmp_path: Path) -> None:
    graph = build(LocalRepositoryAnalyzer().analyze(tmp_path, AnalysisOptions()))
    assert graph.summary.total_nodes == 1
    assert graph.summary.total_edges == 0
    assert not graph.summary.partial
    assert QueryRepositoryGraph(graph).cycles() == ()


def test_skipped_files_preserved(tmp_path: Path) -> None:
    (tmp_path / "oversized.py").write_text("# large\n" * 100)
    snapshot = LocalRepositoryAnalyzer().analyze(tmp_path, AnalysisOptions(max_file_bytes=100))
    graph = build(snapshot)
    node = QueryRepositoryGraph(graph).node("file:oversized.py")
    assert node.file is not None and node.file.parse_status.value == "skipped"
    assert graph.summary.partial
    assert decode_graph(canonical_graph(graph)) == graph


def test_exact_duplicate_occurrence_identity(tmp_path: Path) -> None:
    from archguard.domain.repository import summarize

    (tmp_path / "a.py").write_text("import external\n")
    snapshot = LocalRepositoryAnalyzer().analyze(tmp_path, AnalysisOptions())
    file = snapshot.files[0]
    files = (replace(file, imports=file.imports * 2),)
    duplicate = replace(snapshot, files=files, summary=summarize(files, snapshot.diagnostics))
    graph = build(duplicate)
    imports = [edge for edge in graph.edges if edge.kind == EdgeKind.IMPORTS]
    assert sorted(edge.occurrence for edge in imports) == [1, 2]
    assert len({edge.identifier for edge in imports}) == 2
    assert decode_graph(canonical_graph(graph)) == graph
