"""Immutable directed multigraph contract, with no storage or third-party dependencies."""

import hashlib
from collections import Counter
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Literal

from archguard.domain.canonical import canonical_json
from archguard.domain.enums import Severity
from archguard.domain.repository import (
    ImportSnapshot,
    ParseStatus,
    SourceFileSnapshot,
    SymbolSnapshot,
    check,
    digest,
    dotted_name,
    safe_path,
)

GRAPH_SCHEMA_VERSION = "1"


class NodeKind(StrEnum):
    REPOSITORY = "repository"
    FILE = "file"
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    ASYNC_FUNCTION = "async_function"
    EXTERNAL_MODULE = "external_module"


class EdgeKind(StrEnum):
    CONTAINS = "contains"
    DEFINES = "defines"
    IMPORTS = "imports"


class Resolution(StrEnum):
    INTERNAL = "internal"
    EXTERNAL = "external"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"


class GraphDiagnosticCode(StrEnum):
    AMBIGUOUS_MODULE = "ambiguous_module_ownership"
    UNRESOLVED_RELATIVE = "unresolved_relative_import"
    BEYOND_ROOT = "relative_import_beyond_root"
    INVALID_IMPORTER = "invalid_importing_module"
    AMBIGUOUS_IMPORT = "ambiguous_import"
    INVALID_REFERENCE = "invalid_graph_reference"
    UNSUPPORTED_SNAPSHOT = "unsupported_snapshot_version"
    INCOMPLETE_SNAPSHOT = "incomplete_source_snapshot"
    CONFLICTING_NODE = "conflicting_node_identity"


GRAPH_MESSAGES = {
    GraphDiagnosticCode.AMBIGUOUS_MODULE: "Ambiguous module ownership was omitted.",
    GraphDiagnosticCode.UNRESOLVED_RELATIVE: "Relative import has no unique local target.",
    GraphDiagnosticCode.BEYOND_ROOT: "Relative import exceeds the derived package root.",
    GraphDiagnosticCode.INVALID_IMPORTER: "Importing file has no valid module identity.",
    GraphDiagnosticCode.AMBIGUOUS_IMPORT: "Import resolution involves ambiguous module ownership.",
    GraphDiagnosticCode.INVALID_REFERENCE: "Graph reference violates structural invariants.",
    GraphDiagnosticCode.UNSUPPORTED_SNAPSHOT: "Source snapshot version is unsupported.",
    GraphDiagnosticCode.INCOMPLETE_SNAPSHOT: "Source snapshot is incomplete.",
    GraphDiagnosticCode.CONFLICTING_NODE: "Graph node identity is conflicting.",
}


class GraphValidationError(ValueError):
    def __init__(self, code: GraphDiagnosticCode) -> None:
        self.code = code
        super().__init__(GRAPH_MESSAGES[code])


@dataclass(frozen=True)
class GraphBuildOptions:
    external_names: Literal["full_module", "top_level"] = "full_module"

    def __post_init__(self) -> None:
        check(
            self.external_names in {"full_module", "top_level"}, "unsupported external-name policy"
        )


@dataclass(frozen=True)
class GraphFile:
    path: str
    sha256: str | None
    byte_size: int
    line_count: int
    module_name: str | None
    package_initializer: bool
    parse_status: ParseStatus
    import_count: int
    symbol_count: int

    def __post_init__(self) -> None:
        SourceFileSnapshot(
            self.path,
            self.sha256,
            self.byte_size,
            self.line_count,
            self.module_name,
            self.package_initializer,
            self.parse_status,
        )
        check(self.import_count >= 0 and self.symbol_count >= 0, "invalid file metadata counts")
        check(
            self.parse_status == ParseStatus.PARSED
            or (self.import_count == self.symbol_count == 0),
            "unparsed file cannot have AST metadata counts",
        )

    @classmethod
    def from_snapshot(cls, source: SourceFileSnapshot) -> "GraphFile":
        return cls(
            source.path,
            source.sha256,
            source.byte_size,
            source.line_count,
            source.module_name,
            source.package_initializer,
            source.parse_status,
            len(source.imports),
            len(source.symbols),
        )


@dataclass(frozen=True)
class GraphNode:
    identifier: str
    kind: NodeKind
    file: GraphFile | None = None
    symbol: SymbolSnapshot | None = None
    module_name: str | None = None
    owner_path: str | None = None

    def __post_init__(self) -> None:
        check(isinstance(self.kind, NodeKind), "invalid node kind")
        if self.kind == NodeKind.REPOSITORY:
            check(
                self.identifier == "repository:root"
                and all(
                    x is None for x in (self.file, self.symbol, self.module_name, self.owner_path)
                ),
                "invalid repository node",
            )
        elif self.kind == NodeKind.FILE:
            check(
                self.file is not None
                and self.symbol is None
                and self.module_name is None
                and self.owner_path is None,
                "invalid file node metadata",
            )
            assert self.file is not None
            check(self.identifier == "file:" + self.file.path, "invalid file node ID")
        elif self.kind in {NodeKind.MODULE, NodeKind.EXTERNAL_MODULE}:
            check(
                self.file is None and self.symbol is None and dotted_name(self.module_name or ""),
                "invalid module node metadata",
            )
            prefix = "module:" if self.kind == NodeKind.MODULE else "external-module:"
            check(self.identifier == prefix + str(self.module_name), "invalid module node ID")
            if self.kind == NodeKind.MODULE:
                check(self.owner_path is not None, "module requires an owner")
                assert self.owner_path is not None
                safe_path(self.owner_path)
            else:
                check(self.owner_path is None, "external module cannot own local source")
        else:
            check(
                self.symbol is not None
                and self.file is None
                and self.module_name is None
                and self.owner_path is None,
                "invalid symbol node metadata",
            )
            assert self.symbol is not None
            check(
                self.identifier == self.symbol.identifier
                and self.kind.value == self.symbol.kind.value,
                "invalid symbol node identity",
            )


def edge_identifier(
    kind: EdgeKind,
    source: str,
    target: str,
    record: ImportSnapshot | None = None,
    resolution: Resolution | None = None,
    occurrence: int = 0,
) -> str:
    identity = {
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "kind": kind,
        "source": source,
        "target": target,
        "import_record": asdict(record) if record else None,
        "resolution": resolution,
        "occurrence": occurrence,
    }
    return "edge:" + hashlib.sha256(canonical_json(identity)).hexdigest()


@dataclass(frozen=True)
class GraphEdge:
    identifier: str
    source: str
    target: str
    kind: EdgeKind
    import_record: ImportSnapshot | None = None
    resolution: Resolution | None = None
    occurrence: int = 0

    def __post_init__(self) -> None:
        check(isinstance(self.kind, EdgeKind), "invalid edge kind")
        if self.kind == EdgeKind.IMPORTS:
            check(
                self.import_record is not None
                and self.resolution in {Resolution.INTERNAL, Resolution.EXTERNAL}
                and self.occurrence > 0,
                "invalid import edge metadata",
            )
        else:
            check(
                self.import_record is None and self.resolution is None and self.occurrence == 0,
                "structural edge cannot contain import metadata",
            )
        check(
            self.identifier
            == edge_identifier(
                self.kind,
                self.source,
                self.target,
                self.import_record,
                self.resolution,
                self.occurrence,
            ),
            "edge identity mismatch",
        )

    @classmethod
    def create(
        cls,
        kind: EdgeKind,
        source: str,
        target: str,
        record: ImportSnapshot | None = None,
        resolution: Resolution | None = None,
        occurrence: int = 0,
    ) -> "GraphEdge":
        return cls(
            edge_identifier(kind, source, target, record, resolution, occurrence),
            source,
            target,
            kind,
            record,
            resolution,
            occurrence,
        )


@dataclass(frozen=True)
class GraphDiagnostic:
    code: GraphDiagnosticCode
    severity: Severity
    message: str
    path: str | None = None
    line: int | None = None
    column: int | None = None
    import_record: ImportSnapshot | None = None
    resolution: Resolution | None = None
    occurrence: int = 0

    def __post_init__(self) -> None:
        check(self.message == GRAPH_MESSAGES[self.code], "invalid graph diagnostic message")
        check(
            self.severity
            == (
                Severity.WARNING
                if self.code == GraphDiagnosticCode.INCOMPLETE_SNAPSHOT
                else Severity.ERROR
            ),
            "invalid diagnostic severity",
        )
        if self.path is not None:
            safe_path(self.path)
        if self.import_record is not None:
            record = self.import_record
            check(
                (self.path, self.line, self.column) == (record.path, record.line, record.column),
                "diagnostic import location mismatch",
            )
            check(
                self.resolution in {Resolution.UNRESOLVED, Resolution.AMBIGUOUS}
                and self.occurrence > 0,
                "invalid unresolved import metadata",
            )
        else:
            check(
                self.line is None
                and self.column is None
                and self.resolution is None
                and self.occurrence == 0,
                "invalid non-import diagnostic metadata",
            )

    @property
    def sort_key(self) -> bytes:
        return canonical_json(asdict(self))

    @classmethod
    def create(
        cls,
        code: GraphDiagnosticCode,
        path: str | None = None,
        record: ImportSnapshot | None = None,
        resolution: Resolution | None = None,
        occurrence: int = 0,
    ) -> "GraphDiagnostic":
        return cls(
            code,
            Severity.WARNING if code == GraphDiagnosticCode.INCOMPLETE_SNAPSHOT else Severity.ERROR,
            GRAPH_MESSAGES[code],
            path,
            record.line if record else None,
            record.column if record else None,
            record,
            resolution,
            occurrence,
        )


@dataclass(frozen=True)
class GraphSummary:
    total_nodes: int
    total_edges: int
    repository_nodes: int
    file_nodes: int
    module_nodes: int
    class_nodes: int
    function_nodes: int
    async_function_nodes: int
    external_module_nodes: int
    containment_edges: int
    definition_edges: int
    import_edges: int
    internal_imports: int
    external_imports: int
    unresolved_imports: int
    ambiguous_imports: int
    diagnostic_count: int
    partial: bool
    unique_internal_module_dependencies: int


def summarize_graph(
    nodes: tuple[GraphNode, ...],
    edges: tuple[GraphEdge, ...],
    diagnostics: tuple[GraphDiagnostic, ...],
    input_partial: bool,
) -> GraphSummary:
    kinds = Counter(n.kind for n in nodes)
    edge_kinds = Counter(e.kind for e in edges)
    return GraphSummary(
        len(nodes),
        len(edges),
        kinds[NodeKind.REPOSITORY],
        kinds[NodeKind.FILE],
        kinds[NodeKind.MODULE],
        kinds[NodeKind.CLASS],
        kinds[NodeKind.FUNCTION],
        kinds[NodeKind.ASYNC_FUNCTION],
        kinds[NodeKind.EXTERNAL_MODULE],
        edge_kinds[EdgeKind.CONTAINS],
        edge_kinds[EdgeKind.DEFINES],
        edge_kinds[EdgeKind.IMPORTS],
        sum(e.resolution == Resolution.INTERNAL for e in edges),
        sum(e.resolution == Resolution.EXTERNAL for e in edges),
        sum(d.resolution == Resolution.UNRESOLVED for d in diagnostics),
        sum(d.resolution == Resolution.AMBIGUOUS for d in diagnostics),
        len(diagnostics),
        input_partial or bool(diagnostics),
        len({(e.source, e.target) for e in edges if e.resolution == Resolution.INTERNAL}),
    )


def graph_identity(
    snapshot_fingerprint: str,
    options: GraphBuildOptions,
    nodes: tuple[GraphNode, ...],
    edges: tuple[GraphEdge, ...],
    diagnostics: tuple[GraphDiagnostic, ...],
    input_partial: bool,
) -> str:
    return hashlib.sha256(
        canonical_json(
            {
                "graph_schema_version": GRAPH_SCHEMA_VERSION,
                "snapshot_fingerprint": snapshot_fingerprint,
                "build_options": asdict(options),
                "nodes": [asdict(n) for n in nodes],
                "edges": [asdict(e) for e in edges],
                "diagnostics": [asdict(d) for d in diagnostics],
                "input_partial": input_partial,
            }
        )
    ).hexdigest()


@dataclass(frozen=True)
class RepositoryGraph:
    graph_schema_version: str
    snapshot_fingerprint: str
    build_options: GraphBuildOptions
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    diagnostics: tuple[GraphDiagnostic, ...]
    input_partial: bool
    summary: GraphSummary
    graph_fingerprint: str

    def __post_init__(self) -> None:
        from archguard.domain.graph_validation import validate_graph

        check(self.graph_schema_version == GRAPH_SCHEMA_VERSION, "unsupported graph schema")
        digest(self.snapshot_fingerprint)
        digest(self.graph_fingerprint)
        for field in ("nodes", "edges", "diagnostics"):
            object.__setattr__(self, field, tuple(getattr(self, field)))
        check(
            [n.identifier for n in self.nodes] == sorted({n.identifier for n in self.nodes}),
            "nodes must be unique and ordered",
        )
        check(
            [e.identifier for e in self.edges] == sorted({e.identifier for e in self.edges}),
            "edges must be unique and ordered",
        )
        check(
            self.diagnostics == tuple(sorted(self.diagnostics, key=lambda d: d.sort_key)),
            "diagnostics must be ordered",
        )
        check(
            self.summary
            == summarize_graph(self.nodes, self.edges, self.diagnostics, self.input_partial),
            "graph summary mismatch",
        )
        validate_graph(self)
        check(
            self.graph_fingerprint
            == graph_identity(
                self.snapshot_fingerprint,
                self.build_options,
                self.nodes,
                self.edges,
                self.diagnostics,
                self.input_partial,
            ),
            "graph fingerprint mismatch",
        )

    @classmethod
    def create(
        cls,
        snapshot_fingerprint: str,
        options: GraphBuildOptions,
        nodes: tuple[GraphNode, ...],
        edges: tuple[GraphEdge, ...],
        diagnostics: tuple[GraphDiagnostic, ...],
        input_partial: bool,
    ) -> "RepositoryGraph":
        return cls(
            GRAPH_SCHEMA_VERSION,
            snapshot_fingerprint,
            options,
            nodes,
            edges,
            diagnostics,
            input_partial,
            summarize_graph(nodes, edges, diagnostics, input_partial),
            graph_identity(snapshot_fingerprint, options, nodes, edges, diagnostics, input_partial),
        )
