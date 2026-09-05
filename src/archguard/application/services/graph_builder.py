"""Pure graph construction from snapshot metadata, without repository access."""

from collections import Counter
from dataclasses import asdict

from archguard.domain.canonical import canonical_json
from archguard.domain.graph import (
    EdgeKind,
    GraphBuildOptions,
    GraphDiagnostic,
    GraphDiagnosticCode,
    GraphEdge,
    GraphFile,
    GraphNode,
    GraphValidationError,
    NodeKind,
    RepositoryGraph,
    Resolution,
)
from archguard.domain.graph_resolution import resolve_import
from archguard.domain.graph_validation import structural_edges
from archguard.domain.repository import SCHEMA_VERSION, RepositorySnapshot


class DeterministicGraphBuilder:
    def build(self, snapshot: RepositorySnapshot, options: GraphBuildOptions) -> RepositoryGraph:
        if snapshot.schema_version != SCHEMA_VERSION:
            raise GraphValidationError(GraphDiagnosticCode.UNSUPPORTED_SNAPSHOT)
        nodes = [GraphNode("repository:root", NodeKind.REPOSITORY)]
        files = {f.path: GraphFile.from_snapshot(f) for f in snapshot.files}
        owners = Counter(f.module_name for f in files.values() if f.module_name is not None)
        diagnostics: list[GraphDiagnostic] = []
        if snapshot.partial:
            diagnostics.append(GraphDiagnostic.create(GraphDiagnosticCode.INCOMPLETE_SNAPSHOT))
        for file in files.values():
            nodes.append(GraphNode("file:" + file.path, NodeKind.FILE, file=file))
            if file.module_name is not None:
                if owners[file.module_name] == 1:
                    nodes.append(
                        GraphNode(
                            "module:" + file.module_name,
                            NodeKind.MODULE,
                            module_name=file.module_name,
                            owner_path=file.path,
                        )
                    )
                else:
                    diagnostics.append(
                        GraphDiagnostic.create(GraphDiagnosticCode.AMBIGUOUS_MODULE, file.path)
                    )
        symbols = tuple(s for f in snapshot.files for s in f.symbols)
        nodes.extend(GraphNode(s.identifier, NodeKind(s.kind.value), symbol=s) for s in symbols)
        edges = list(structural_edges(files, symbols))
        external: set[str] = set()
        occurrences: Counter[bytes] = Counter()
        for source in snapshot.files:
            file = files[source.path]
            for record in source.imports:
                key = canonical_json(asdict(record))
                occurrences[key] += 1
                occurrence = occurrences[key]
                status, target, code = resolve_import(file, record, owners, options)
                if target is None:
                    assert code is not None
                    diagnostics.append(
                        GraphDiagnostic.create(code, source.path, record, status, occurrence)
                    )
                else:
                    edges.append(
                        GraphEdge.create(
                            EdgeKind.IMPORTS,
                            "module:" + str(source.module_name),
                            target,
                            record,
                            status,
                            occurrence,
                        )
                    )
                    if status == Resolution.EXTERNAL:
                        external.add(target)
        nodes.extend(
            GraphNode(
                target,
                NodeKind.EXTERNAL_MODULE,
                module_name=target.removeprefix("external-module:"),
            )
            for target in sorted(external)
        )
        if len({n.identifier for n in nodes}) != len(nodes):
            raise GraphValidationError(GraphDiagnosticCode.CONFLICTING_NODE)
        return RepositoryGraph.create(
            snapshot.repository_fingerprint,
            options,
            tuple(sorted(nodes, key=lambda n: n.identifier)),
            tuple(sorted(edges, key=lambda e: e.identifier)),
            tuple(sorted(diagnostics, key=lambda d: d.sort_key)),
            snapshot.partial,
        )
