"""Graph-wide referential, ownership, containment and import invariants."""

from collections import Counter, defaultdict
from dataclasses import asdict

from archguard.domain.canonical import canonical_json
from archguard.domain.graph import (
    EdgeKind,
    GraphDiagnostic,
    GraphDiagnosticCode,
    GraphEdge,
    GraphFile,
    GraphValidationError,
    NodeKind,
    RepositoryGraph,
    Resolution,
)
from archguard.domain.graph_resolution import resolve_import
from archguard.domain.repository import (
    ImportSnapshot,
    ParseStatus,
    SourceFileSnapshot,
    SymbolSnapshot,
    check,
)


def structural_edges(
    files: dict[str, GraphFile], symbols: tuple[SymbolSnapshot, ...]
) -> tuple[GraphEdge, ...]:
    owners = Counter(f.module_name for f in files.values() if f.module_name is not None)
    edges: list[GraphEdge] = []
    grouped: dict[str, list[SymbolSnapshot]] = defaultdict(list)
    for symbol in symbols:
        check(symbol.path in files, "symbol requires an existing file")
        grouped[symbol.path].append(symbol)
    for path, file in files.items():
        file_id = "file:" + path
        edges.append(GraphEdge.create(EdgeKind.CONTAINS, "repository:root", file_id))
        unique = file.module_name is not None and owners[file.module_name] == 1
        owner = "module:" + str(file.module_name) if unique else file_id
        if unique:
            edges.append(GraphEdge.create(EdgeKind.DEFINES, file_id, owner))
        ordered = tuple(sorted(grouped[path], key=lambda s: (s.start_line, s.column, s.identifier)))
        SourceFileSnapshot(
            path,
            file.sha256,
            file.byte_size,
            file.line_count,
            file.module_name,
            file.package_initializer,
            file.parse_status,
            symbols=ordered,
        )
        check(len(ordered) == file.symbol_count, "file symbol count mismatch")
        stack: list[SymbolSnapshot] = []
        for symbol in ordered:
            while stack and symbol.start_line > stack[-1].end_line:
                stack.pop()
            source = stack[-1].identifier if stack else owner
            kind = EdgeKind.CONTAINS if stack else EdgeKind.DEFINES
            edges.append(GraphEdge.create(kind, source, symbol.identifier))
            stack.append(symbol)
    return tuple(sorted(edges, key=lambda e: e.identifier))


def validate_graph(graph: RepositoryGraph) -> None:
    nodes = {node.identifier: node for node in graph.nodes}
    check(
        sum(n.kind == NodeKind.REPOSITORY for n in graph.nodes) == 1,
        "exactly one repository required",
    )
    files = {n.file.path: n.file for n in graph.nodes if n.file is not None}
    owners = Counter(f.module_name for f in files.values() if f.module_name is not None)
    expected_modules = {
        "module:" + str(f.module_name): f.path
        for f in files.values()
        if f.module_name is not None and owners[f.module_name] == 1
    }
    check(
        {n.identifier: n.owner_path for n in graph.nodes if n.kind == NodeKind.MODULE}
        == expected_modules,
        "ambiguous or missing module ownership",
    )
    expected_diagnostics = [
        GraphDiagnostic.create(GraphDiagnosticCode.AMBIGUOUS_MODULE, f.path)
        for f in files.values()
        if f.module_name is not None and owners[f.module_name] > 1
    ]
    if any(f.parse_status != ParseStatus.PARSED or f.module_name is None for f in files.values()):
        check(graph.input_partial, "incomplete files require partial input status")
    if graph.input_partial:
        expected_diagnostics.append(GraphDiagnostic.create(GraphDiagnosticCode.INCOMPLETE_SNAPSHOT))
    expected_structural = structural_edges(
        files, tuple(n.symbol for n in graph.nodes if n.symbol is not None)
    )
    actual_structural = tuple(e for e in graph.edges if e.kind != EdgeKind.IMPORTS)
    check(actual_structural == expected_structural, "invalid structural edge set")
    occurrences: dict[bytes, list[int]] = defaultdict(list)
    counts: Counter[str] = Counter()
    external_targets: set[str] = set()

    def validate_record(record: ImportSnapshot, occurrence: int) -> GraphFile:
        check(record.path in files, "import requires an existing file")
        file = files[record.path]
        check(
            file.parse_status == ParseStatus.PARSED and record.line <= file.line_count,
            "invalid import source location",
        )
        counts[record.path] += 1
        occurrences[canonical_json(asdict(record))].append(occurrence)
        return file

    for edge in graph.edges:
        if edge.source not in nodes or edge.target not in nodes:
            raise GraphValidationError(GraphDiagnosticCode.INVALID_REFERENCE)
        if edge.import_record is None:
            continue
        file = validate_record(edge.import_record, edge.occurrence)
        resolution, target, code = resolve_import(
            file, edge.import_record, owners, graph.build_options
        )
        check(
            code is None
            and target == edge.target
            and resolution == edge.resolution
            and edge.source == "module:" + str(file.module_name),
            "import edge resolution mismatch",
        )
        if resolution == Resolution.EXTERNAL:
            external_targets.add(edge.target)
    for diagnostic in graph.diagnostics:
        if diagnostic.import_record is None:
            continue
        file = validate_record(diagnostic.import_record, diagnostic.occurrence)
        resolution, target, code = resolve_import(
            file, diagnostic.import_record, owners, graph.build_options
        )
        check(
            target is None and code == diagnostic.code and resolution == diagnostic.resolution,
            "unresolved import diagnostic mismatch",
        )
        expected_diagnostics.append(diagnostic)
    check(
        graph.diagnostics == tuple(sorted(expected_diagnostics, key=lambda d: d.sort_key)),
        "graph diagnostic set mismatch",
    )
    check(
        all(counts[path] == file.import_count for path, file in files.items()),
        "missing import occurrences",
    )
    check(
        all(sorted(values) == list(range(1, len(values) + 1)) for values in occurrences.values()),
        "duplicate or missing import occurrence identity",
    )
    check(
        {n.identifier for n in graph.nodes if n.kind == NodeKind.EXTERNAL_MODULE}
        == external_targets,
        "external node reference mismatch",
    )
