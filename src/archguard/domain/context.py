"""Immutable, provider-neutral contracts for deterministic context retrieval."""

import hashlib
from dataclasses import asdict, dataclass, is_dataclass
from enum import StrEnum
from typing import Any

from archguard.domain.canonical import canonical_json
from archguard.domain.graph import EdgeKind, NodeKind
from archguard.domain.repository import check, digest, dotted_name, safe_path

QUERY_SCHEMA_VERSION = "1"
POLICY_SCHEMA_VERSION = "1"
MANIFEST_SCHEMA_VERSION = "1"
BUNDLE_SCHEMA_VERSION = "1"
LABELS_SCHEMA_VERSION = "1"
EVALUATION_SCHEMA_VERSION = "1"
METHOD_ID = "deterministic-graph-retrieval-v1"
METHOD_VERSION = "1"
MAX_QUERY_TERMS = 512
MAX_QUERY_REFERENCES = 256
MAX_GRAPH_DEPTH = 4
MAX_FILES = 256
MAX_SYMBOLS = 2048
MAX_EXCERPTS = 512
MAX_LINES = 100_000
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_MANIFEST_CANDIDATES = 10_000


def fingerprint(value: Any, omitted: str) -> str:
    data = asdict(value)
    data.pop(omitted, None)
    return hashlib.sha256(canonical_json(data)).hexdigest()


def values_fingerprint(values: dict[str, Any]) -> str:
    def plain(value: Any) -> Any:
        if is_dataclass(value):
            return asdict(value)  # type: ignore[arg-type]
        if isinstance(value, dict):
            return {key: plain(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return [plain(item) for item in value]
        return value

    return hashlib.sha256(canonical_json(plain(values))).hexdigest()


class SelectionState(StrEnum):
    SELECTED = "selected"
    EXCLUDED = "excluded"
    TRUNCATED = "truncated"


@dataclass(frozen=True, order=True)
class QueryDiagnostic:
    code: str
    reference_hash: str

    def __post_init__(self) -> None:
        check(self.code.isidentifier(), "invalid query diagnostic")
        digest(self.reference_hash)


@dataclass(frozen=True)
class CompiledRetrievalQuery:
    retrieval_query_schema_version: str
    query_id: str
    normalized_terms: tuple[str, ...]
    explicit_paths: tuple[str, ...]
    traceback_paths: tuple[str, ...]
    module_ids: tuple[str, ...]
    node_ids: tuple[str, ...]
    symbol_names: tuple[str, ...]
    architecture_node_ids: tuple[str, ...]
    changed_paths: tuple[str, ...]
    text_hashes: tuple[str, ...]
    diagnostics: tuple[QueryDiagnostic, ...]
    query_fingerprint: str

    def __post_init__(self) -> None:
        check(
            self.retrieval_query_schema_version == QUERY_SCHEMA_VERSION, "unsupported query schema"
        )
        check(bool(self.query_id) and len(self.query_id) <= 128, "invalid query ID")
        for field_name in (
            "normalized_terms",
            "explicit_paths",
            "traceback_paths",
            "module_ids",
            "node_ids",
            "symbol_names",
            "architecture_node_ids",
            "changed_paths",
            "text_hashes",
            "diagnostics",
        ):
            field_value = tuple(getattr(self, field_name))
            object.__setattr__(self, field_name, field_value)
            check(
                field_value == tuple(sorted(set(field_value))),
                f"{field_name} must be unique and ordered",
            )
        check(len(self.normalized_terms) <= MAX_QUERY_TERMS, "too many query terms")
        check(
            sum(
                map(
                    len,
                    (
                        self.explicit_paths,
                        self.traceback_paths,
                        self.module_ids,
                        self.node_ids,
                        self.symbol_names,
                        self.architecture_node_ids,
                        self.changed_paths,
                    ),
                )
            )
            <= MAX_QUERY_REFERENCES,
            "too many query references",
        )
        for path in self.explicit_paths + self.traceback_paths + self.changed_paths:
            safe_path(path)
        for name in self.module_ids:
            check(dotted_name(name), "invalid module reference")
        for value in self.text_hashes:
            digest(value)
        check(
            self.query_fingerprint == fingerprint(self, "query_fingerprint"),
            "query fingerprint mismatch",
        )

    @classmethod
    def create(
        cls,
        query_id: str,
        terms: tuple[str, ...],
        paths: tuple[str, ...] = (),
        traceback_paths: tuple[str, ...] = (),
        modules: tuple[str, ...] = (),
        nodes: tuple[str, ...] = (),
        symbols: tuple[str, ...] = (),
        architecture_nodes: tuple[str, ...] = (),
        changed_paths: tuple[str, ...] = (),
        text_hashes: tuple[str, ...] = (),
        diagnostics: tuple[QueryDiagnostic, ...] = (),
    ) -> "CompiledRetrievalQuery":
        values = dict(
            retrieval_query_schema_version=QUERY_SCHEMA_VERSION,
            query_id=query_id,
            normalized_terms=tuple(sorted(set(terms))),
            explicit_paths=tuple(sorted(set(paths))),
            traceback_paths=tuple(sorted(set(traceback_paths))),
            module_ids=tuple(sorted(set(modules))),
            node_ids=tuple(sorted(set(nodes))),
            symbol_names=tuple(sorted(set(symbols))),
            architecture_node_ids=tuple(sorted(set(architecture_nodes))),
            changed_paths=tuple(sorted(set(changed_paths))),
            text_hashes=tuple(sorted(set(text_hashes))),
            diagnostics=tuple(sorted(set(diagnostics))),
        )
        return cls(
            QUERY_SCHEMA_VERSION,
            query_id,
            values["normalized_terms"],  # type: ignore[arg-type]
            values["explicit_paths"],  # type: ignore[arg-type]
            values["traceback_paths"],  # type: ignore[arg-type]
            values["module_ids"],  # type: ignore[arg-type]
            values["node_ids"],  # type: ignore[arg-type]
            values["symbol_names"],  # type: ignore[arg-type]
            values["architecture_node_ids"],  # type: ignore[arg-type]
            values["changed_paths"],  # type: ignore[arg-type]
            values["text_hashes"],  # type: ignore[arg-type]
            values["diagnostics"],  # type: ignore[arg-type]
            values_fingerprint(values),
        )


@dataclass(frozen=True)
class RetrievalPolicy:
    retrieval_policy_schema_version: str = POLICY_SCHEMA_VERSION
    max_depth: int = 2
    allowed_edge_kinds: tuple[EdgeKind, ...] = (
        EdgeKind.CONTAINS,
        EdgeKind.DEFINES,
        EdgeKind.IMPORTS,
    )
    include_tests: bool = True
    include_generated: bool = False
    include_external: bool = False
    max_files: int = 12
    max_symbols: int = 30
    max_excerpts: int = 30
    max_lines: int = 500
    max_source_bytes: int = 50_000
    max_manifest_candidates: int = 500
    per_file_excerpt_limit: int = 3
    context_before: int = 2
    context_after: int = 2
    include_patterns: tuple[str, ...] = ()
    exclude_patterns: tuple[str, ...] = ()
    policy_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.retrieval_policy_schema_version == POLICY_SCHEMA_VERSION, "unsupported policy")
        bounds = (
            (self.max_depth, 0, MAX_GRAPH_DEPTH),
            (self.max_files, 0, MAX_FILES),
            (self.max_symbols, 0, MAX_SYMBOLS),
            (self.max_excerpts, 0, MAX_EXCERPTS),
            (self.max_lines, 0, MAX_LINES),
            (self.max_source_bytes, 0, MAX_SOURCE_BYTES),
            (self.max_manifest_candidates, 1, MAX_MANIFEST_CANDIDATES),
            (self.per_file_excerpt_limit, 1, 100),
            (self.context_before, 0, 100),
            (self.context_after, 0, 100),
        )
        check(
            all(low <= value <= high for value, low, high in bounds), "retrieval limit out of range"
        )
        for field in ("allowed_edge_kinds", "include_patterns", "exclude_patterns"):
            value = tuple(sorted(set(getattr(self, field))))
            object.__setattr__(self, field, value)
        expected = fingerprint(self, "policy_fingerprint")
        if self.policy_fingerprint:
            check(self.policy_fingerprint == expected, "policy fingerprint mismatch")
        else:
            object.__setattr__(self, "policy_fingerprint", expected)


@dataclass(frozen=True, order=True)
class ScoreComponent:
    name: str
    value: int

    def __post_init__(self) -> None:
        check(
            self.name.isidentifier() and -1_000_000 <= self.value <= 1_000_000,
            "invalid score component",
        )


@dataclass(frozen=True, order=True)
class RetrievalSeed:
    seed_id: str
    seed_type: str
    node_id: str
    evidence_hash: str
    base_score: int
    ambiguous: bool
    explanation: str

    def __post_init__(self) -> None:
        digest(self.evidence_hash)
        check(self.seed_id.startswith("seed:"), "invalid seed ID")
        check(0 < self.base_score <= 1_000_000, "invalid seed score")
        check(self.seed_type.isidentifier(), "invalid seed type")


@dataclass(frozen=True)
class RetrievalCandidate:
    rank: int
    node_id: str
    node_kind: NodeKind
    path: str | None
    module_id: str | None
    symbol_name: str | None
    line_start: int | None
    line_end: int | None
    total_score: int
    score_components: tuple[ScoreComponent, ...]
    graph_distance: int
    seed_ids: tuple[str, ...]
    relationship_path: tuple[str, ...]
    alternative_shortest_paths: int
    selection_state: SelectionState
    decision_reason: str
    estimated_lines: int
    estimated_bytes: int

    def __post_init__(self) -> None:
        check(self.rank > 0 and self.graph_distance >= 0, "invalid candidate rank or distance")
        check(isinstance(self.node_kind, NodeKind), "invalid candidate node kind")
        if self.path is not None:
            safe_path(self.path)
        check((self.line_start is None) == (self.line_end is None), "incomplete line range")
        if self.line_start is not None:
            assert self.line_end is not None
            check(1 <= self.line_start <= self.line_end, "invalid line range")
        object.__setattr__(self, "score_components", tuple(self.score_components))
        object.__setattr__(self, "seed_ids", tuple(sorted(set(self.seed_ids))))
        object.__setattr__(self, "relationship_path", tuple(self.relationship_path))
        check(self.score_components == tuple(sorted(self.score_components)), "unordered scores")
        check(self.total_score == sum(c.value for c in self.score_components), "score mismatch")
        check(self.alternative_shortest_paths > 0, "invalid path count")
        check(self.estimated_lines >= 0 and self.estimated_bytes >= 0, "invalid source cost")


@dataclass(frozen=True)
class BudgetSummary:
    selected_files: int
    selected_symbols: int
    selected_excerpts: int
    consumed_lines: int
    consumed_bytes: int

    def __post_init__(self) -> None:
        check(all(v >= 0 for v in asdict(self).values()), "negative budget accounting")


@dataclass(frozen=True)
class RetrievalManifest:
    retrieval_manifest_schema_version: str
    method_id: str
    method_version: str
    query_fingerprint: str
    snapshot_fingerprint: str
    graph_fingerprint: str
    policy: RetrievalPolicy
    seeds: tuple[RetrievalSeed, ...]
    candidates: tuple[RetrievalCandidate, ...]
    budget: BudgetSummary
    complete: bool
    diagnostics: tuple[str, ...]
    manifest_fingerprint: str

    def __post_init__(self) -> None:
        check(
            self.retrieval_manifest_schema_version == MANIFEST_SCHEMA_VERSION,
            "unsupported manifest",
        )
        check(
            (self.method_id, self.method_version) == (METHOD_ID, METHOD_VERSION),
            "unsupported method",
        )
        for value in (self.query_fingerprint, self.snapshot_fingerprint, self.graph_fingerprint):
            digest(value)
        object.__setattr__(self, "seeds", tuple(self.seeds))
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(self, "diagnostics", tuple(sorted(set(self.diagnostics))))
        check(
            tuple(c.rank for c in self.candidates) == tuple(range(1, len(self.candidates) + 1)),
            "candidate ranks must be contiguous",
        )
        check(
            len({c.node_id for c in self.candidates}) == len(self.candidates), "duplicate candidate"
        )
        selected = [c for c in self.candidates if c.selection_state == SelectionState.SELECTED]
        check(self.budget.selected_excerpts == len(selected), "excerpt budget mismatch")
        check(
            self.budget.selected_files == len({c.path for c in selected if c.path}),
            "file budget mismatch",
        )
        check(
            self.budget.selected_symbols
            == sum(
                c.node_kind in {NodeKind.CLASS, NodeKind.FUNCTION, NodeKind.ASYNC_FUNCTION}
                for c in selected
            ),
            "symbol budget mismatch",
        )
        check(
            self.budget.consumed_lines == sum(c.estimated_lines for c in selected),
            "line budget mismatch",
        )
        check(
            self.budget.consumed_bytes == sum(c.estimated_bytes for c in selected),
            "byte budget mismatch",
        )
        check(
            self.budget.selected_files <= self.policy.max_files
            and self.budget.selected_symbols <= self.policy.max_symbols
            and self.budget.selected_excerpts <= self.policy.max_excerpts
            and self.budget.consumed_lines <= self.policy.max_lines
            and self.budget.consumed_bytes <= self.policy.max_source_bytes,
            "budget exceeded",
        )
        check(
            self.manifest_fingerprint == fingerprint(self, "manifest_fingerprint"),
            "manifest fingerprint mismatch",
        )

    @classmethod
    def create(
        cls,
        query_fingerprint: str,
        snapshot_fingerprint: str,
        graph_fingerprint: str,
        policy: RetrievalPolicy,
        seeds: tuple[RetrievalSeed, ...],
        candidates: tuple[RetrievalCandidate, ...],
        budget: BudgetSummary,
        complete: bool = True,
        diagnostics: tuple[str, ...] = (),
    ) -> "RetrievalManifest":
        values = dict(
            retrieval_manifest_schema_version=MANIFEST_SCHEMA_VERSION,
            method_id=METHOD_ID,
            method_version=METHOD_VERSION,
            query_fingerprint=query_fingerprint,
            snapshot_fingerprint=snapshot_fingerprint,
            graph_fingerprint=graph_fingerprint,
            policy=policy,
            seeds=seeds,
            candidates=candidates,
            budget=budget,
            complete=complete,
            diagnostics=tuple(sorted(set(diagnostics))),
        )
        return cls(
            MANIFEST_SCHEMA_VERSION,
            METHOD_ID,
            METHOD_VERSION,
            query_fingerprint,
            snapshot_fingerprint,
            graph_fingerprint,
            policy,
            seeds,
            candidates,
            budget,
            complete,
            tuple(sorted(set(diagnostics))),
            values_fingerprint(values),
        )


@dataclass(frozen=True)
class SourceExcerpt:
    path: str
    line_start: int
    line_end: int
    utf8_bytes: int
    content_sha256: str
    content: str

    def __post_init__(self) -> None:
        safe_path(self.path)
        check(1 <= self.line_start <= self.line_end, "invalid excerpt range")
        raw = self.content.encode("utf-8")
        check(len(raw) == self.utf8_bytes, "excerpt byte count mismatch")
        check(hashlib.sha256(raw).hexdigest() == self.content_sha256, "excerpt hash mismatch")


@dataclass(frozen=True)
class ContextBundle:
    context_bundle_schema_version: str
    sensitivity: str
    manifest_fingerprint: str
    snapshot_fingerprint: str
    graph_fingerprint: str
    excerpts: tuple[SourceExcerpt, ...]
    total_lines: int
    total_bytes: int
    complete: bool
    diagnostics: tuple[str, ...]
    bundle_fingerprint: str

    def __post_init__(self) -> None:
        check(self.context_bundle_schema_version == BUNDLE_SCHEMA_VERSION, "unsupported bundle")
        check(self.sensitivity == "sensitive-source-bearing", "invalid sensitivity marker")
        for value in (self.manifest_fingerprint, self.snapshot_fingerprint, self.graph_fingerprint):
            digest(value)
        object.__setattr__(self, "excerpts", tuple(self.excerpts))
        check(
            self.excerpts
            == tuple(sorted(self.excerpts, key=lambda x: (x.path, x.line_start, x.line_end))),
            "unordered excerpts",
        )
        check(self.total_bytes == sum(x.utf8_bytes for x in self.excerpts), "bundle byte mismatch")
        check(
            self.total_lines == sum(x.line_end - x.line_start + 1 for x in self.excerpts),
            "bundle line mismatch",
        )
        check(
            self.bundle_fingerprint == fingerprint(self, "bundle_fingerprint"),
            "bundle fingerprint mismatch",
        )

    @classmethod
    def create(
        cls,
        manifest: RetrievalManifest,
        excerpts: tuple[SourceExcerpt, ...],
        complete: bool = True,
        diagnostics: tuple[str, ...] = (),
    ) -> "ContextBundle":
        ordered = tuple(sorted(excerpts, key=lambda x: (x.path, x.line_start, x.line_end)))
        values = dict(
            context_bundle_schema_version=BUNDLE_SCHEMA_VERSION,
            sensitivity="sensitive-source-bearing",
            manifest_fingerprint=manifest.manifest_fingerprint,
            snapshot_fingerprint=manifest.snapshot_fingerprint,
            graph_fingerprint=manifest.graph_fingerprint,
            excerpts=ordered,
            total_lines=sum(x.line_end - x.line_start + 1 for x in ordered),
            total_bytes=sum(x.utf8_bytes for x in ordered),
            complete=complete,
            diagnostics=tuple(sorted(set(diagnostics))),
        )
        return cls(
            BUNDLE_SCHEMA_VERSION,
            "sensitive-source-bearing",
            manifest.manifest_fingerprint,
            manifest.snapshot_fingerprint,
            manifest.graph_fingerprint,
            ordered,
            sum(x.line_end - x.line_start + 1 for x in ordered),
            sum(x.utf8_bytes for x in ordered),
            complete,
            tuple(sorted(set(diagnostics))),
            values_fingerprint(values),
        )


@dataclass(frozen=True)
class RelevanceLabels:
    retrieval_labels_schema_version: str
    relevant_node_ids: tuple[str, ...]
    labels_fingerprint: str

    def __post_init__(self) -> None:
        check(self.retrieval_labels_schema_version == LABELS_SCHEMA_VERSION, "unsupported labels")
        object.__setattr__(self, "relevant_node_ids", tuple(self.relevant_node_ids))
        check(
            self.relevant_node_ids == tuple(sorted(set(self.relevant_node_ids))), "duplicate labels"
        )
        check(
            self.labels_fingerprint == fingerprint(self, "labels_fingerprint"),
            "labels fingerprint mismatch",
        )

    @classmethod
    def create(cls, node_ids: tuple[str, ...]) -> "RelevanceLabels":
        values = dict(
            retrieval_labels_schema_version=LABELS_SCHEMA_VERSION,
            relevant_node_ids=tuple(sorted(set(node_ids))),
        )
        ordered = tuple(sorted(set(node_ids)))
        return cls(
            LABELS_SCHEMA_VERSION,
            ordered,
            values_fingerprint(values),
        )


@dataclass(frozen=True, order=True)
class Metric:
    name: str
    numerator: int
    denominator: int
    value: str

    def __post_init__(self) -> None:
        check(
            bool(self.name) and self.denominator > 0 and 0 <= self.numerator <= self.denominator,
            "invalid metric",
        )


@dataclass(frozen=True)
class RetrievalEvaluation:
    retrieval_evaluation_schema_version: str
    metric_version: str
    manifest_fingerprint: str
    labels_fingerprint: str
    ranked_candidate_count: int
    relevant_candidate_count: int
    missing_relevant_references: tuple[str, ...]
    metrics: tuple[Metric, ...]
    complete: bool
    evaluation_fingerprint: str

    def __post_init__(self) -> None:
        check(
            self.retrieval_evaluation_schema_version == EVALUATION_SCHEMA_VERSION,
            "unsupported evaluation",
        )
        check(self.metric_version == "retrieval-metrics-v1", "unsupported metric version")
        digest(self.manifest_fingerprint)
        digest(self.labels_fingerprint)
        object.__setattr__(
            self,
            "missing_relevant_references",
            tuple(sorted(set(self.missing_relevant_references))),
        )
        object.__setattr__(self, "metrics", tuple(self.metrics))
        check(self.metrics == tuple(sorted(self.metrics)), "unordered metrics")
        check(
            self.evaluation_fingerprint == fingerprint(self, "evaluation_fingerprint"),
            "evaluation fingerprint mismatch",
        )

    @classmethod
    def create(
        cls,
        manifest: RetrievalManifest,
        labels: RelevanceLabels,
        missing: tuple[str, ...],
        metrics: tuple[Metric, ...],
    ) -> "RetrievalEvaluation":
        values = dict(
            retrieval_evaluation_schema_version=EVALUATION_SCHEMA_VERSION,
            metric_version="retrieval-metrics-v1",
            manifest_fingerprint=manifest.manifest_fingerprint,
            labels_fingerprint=labels.labels_fingerprint,
            ranked_candidate_count=len(manifest.candidates),
            relevant_candidate_count=len(labels.relevant_node_ids),
            missing_relevant_references=tuple(sorted(set(missing))),
            metrics=tuple(sorted(metrics)),
            complete=manifest.complete and not missing,
        )
        return cls(
            EVALUATION_SCHEMA_VERSION,
            "retrieval-metrics-v1",
            manifest.manifest_fingerprint,
            labels.labels_fingerprint,
            len(manifest.candidates),
            len(labels.relevant_node_ids),
            tuple(sorted(set(missing))),
            tuple(sorted(metrics)),
            manifest.complete and not missing,
            values_fingerprint(values),
        )
