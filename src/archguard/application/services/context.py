"""Deterministic graph retrieval, budgeting, bundling and offline evaluation."""

import hashlib
import re
import unicodedata
from collections import defaultdict, deque
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from fnmatch import fnmatchcase
from pathlib import Path

from archguard.application.ports.context import ContextArtifactPort, SourceExcerptReaderPort
from archguard.domain.context import (
    BudgetSummary,
    CompiledRetrievalQuery,
    ContextBundle,
    Metric,
    QueryDiagnostic,
    RelevanceLabels,
    RetrievalCandidate,
    RetrievalEvaluation,
    RetrievalManifest,
    RetrievalPolicy,
    RetrievalSeed,
    ScoreComponent,
    SelectionState,
)
from archguard.domain.graph import NodeKind, RepositoryGraph
from archguard.domain.repository import RepositorySnapshot, dotted_name, safe_path

MAX_RAW_QUERY_BYTES = 1024 * 1024
STOP_TERMS = frozenset(
    {"a", "an", "and", "at", "for", "from", "in", "is", "of", "on", "or", "the", "to", "with"}
)
TOKEN = re.compile(r"[^\W\d][\w.]*(?:\.[^\W\d][\w.]*)*", re.UNICODE)
TRACE_PATH = re.compile(r'(?:File\s+)?["\']?([^"\'\s]+\.py)["\']?(?:,?\s*line\s+(\d+))?')
KIND_PRIORITY = {
    NodeKind.FILE: 0,
    NodeKind.MODULE: 1,
    NodeKind.CLASS: 2,
    NodeKind.FUNCTION: 3,
    NodeKind.ASYNC_FUNCTION: 4,
    NodeKind.EXTERNAL_MODULE: 5,
    NodeKind.REPOSITORY: 6,
}
BASE = {
    "explicit_path": 10_000,
    "exact_node": 9_500,
    "traceback": 9_000,
    "exact_module": 8_500,
    "exact_symbol": 8_000,
    "architecture_endpoint": 7_800,
    "changed_path": 7_600,
    "lexical": 300,
}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_terms(*texts: str) -> tuple[str, ...]:
    terms: set[str] = set()
    for text in texts:
        normalized = unicodedata.normalize("NFKC", text)
        for token in TOKEN.findall(normalized):
            for part in re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", token).replace(".", " ").split():
                for item in part.split("_"):
                    item = item.casefold()
                    if item and item not in STOP_TERMS:
                        terms.add(item)
    return tuple(sorted(terms))


class CompileRetrievalQuery:
    def execute(
        self,
        query_id: str,
        problem: str,
        error: str = "",
        traceback: str = "",
        paths: tuple[str, ...] = (),
        modules: tuple[str, ...] = (),
        nodes: tuple[str, ...] = (),
        symbols: tuple[str, ...] = (),
        architecture_nodes: tuple[str, ...] = (),
        changed_paths: tuple[str, ...] = (),
    ) -> CompiledRetrievalQuery:
        if not problem.strip():
            raise ValueError("problem statement is empty")
        if any(len(x.encode("utf-8")) > MAX_RAW_QUERY_BYTES for x in (problem, error, traceback)):
            raise ValueError("query text exceeds byte limit")
        trace_paths: list[str] = []
        diagnostics: list[QueryDiagnostic] = []
        for match in TRACE_PATH.finditer(unicodedata.normalize("NFKC", traceback)):
            value = match.group(1).replace("\\", "/")
            while value.startswith("./"):
                value = value[2:]
            try:
                safe_path(value)
                trace_paths.append(value)
            except ValueError:
                diagnostics.append(QueryDiagnostic("unsafe_traceback_path", _hash(value)))
        for value in paths + changed_paths + tuple(trace_paths):
            safe_path(value)
        if any(not dotted_name(value) for value in modules):
            raise ValueError("invalid module reference")
        return CompiledRetrievalQuery.create(
            query_id,
            normalize_terms(problem, error, traceback),
            tuple(paths),
            tuple(trace_paths),
            modules,
            nodes,
            symbols,
            architecture_nodes,
            changed_paths,
            tuple(_hash(x) for x in (problem, error, traceback) if x),
            tuple(diagnostics),
        )


@dataclass(frozen=True)
class RetrievalResult:
    manifest: RetrievalManifest


class RetrieveRepositoryContext:
    def __init__(self, artifacts: ContextArtifactPort) -> None:
        self.artifacts = artifacts

    def execute(
        self,
        snapshot: RepositorySnapshot,
        graph: RepositoryGraph,
        query: CompiledRetrievalQuery,
        policy: RetrievalPolicy,
        output: Path | None = None,
    ) -> RetrievalResult:
        if graph.snapshot_fingerprint != snapshot.repository_fingerprint:
            raise ValueError("snapshot and graph fingerprint mismatch")
        nodes = {n.identifier: n for n in graph.nodes}
        seeds: dict[tuple[str, str, str], RetrievalSeed] = {}

        def add(kind: str, node_id: str, evidence: str, ambiguous: bool = False) -> None:
            score = BASE[kind]
            key = kind, node_id, evidence
            sid = "seed:" + _hash("|".join(key))
            seeds[key] = RetrievalSeed(
                sid,
                kind,
                node_id,
                _hash(evidence),
                score,
                ambiguous,
                kind.replace("_", " ") + " match",
            )

        by_path: dict[str, list[str]] = defaultdict(list)
        by_module: dict[str, list[str]] = defaultdict(list)
        by_symbol: dict[str, list[str]] = defaultdict(list)
        lexical: dict[str, list[str]] = defaultdict(list)
        for node in graph.nodes:
            path = (
                node.file.path
                if node.file
                else node.owner_path or (node.symbol.path if node.symbol else None)
            )
            if path and node.kind == NodeKind.FILE:
                by_path[path].append(node.identifier)
            if path:
                for term in normalize_terms(path):
                    lexical[term].append(node.identifier)
            if node.module_name:
                by_module[node.module_name].append(node.identifier)
                for term in normalize_terms(node.module_name):
                    lexical[term].append(node.identifier)
            if node.symbol:
                for name in {node.symbol.qualified_name, node.symbol.qualified_name.split(".")[-1]}:
                    by_symbol[name].append(node.identifier)
                    for term in normalize_terms(name):
                        lexical[term].append(node.identifier)
            if node.kind == NodeKind.EXTERNAL_MODULE and node.module_name:
                for term in normalize_terms(node.module_name):
                    lexical[term].append(node.identifier)
        unknown: list[str] = []
        for path in query.explicit_paths:
            matches = by_path.get(path, [])
            if not matches:
                unknown.append("unknown_path:" + _hash(path))
            for node_id in matches:
                add("explicit_path", node_id, path, len(matches) > 1)
        for path in query.traceback_paths:
            matches = by_path.get(path, [])
            if not matches:
                unknown.append("unknown_traceback_path:" + _hash(path))
            for node_id in matches:
                add("traceback", node_id, path, len(matches) > 1)
        for path in query.changed_paths:
            matches = by_path.get(path, [])
            if not matches:
                unknown.append("unknown_changed_path:" + _hash(path))
            for node_id in matches:
                add("changed_path", node_id, path, len(matches) > 1)
        for module in query.module_ids:
            matches = by_module.get(module, [])
            if not matches:
                unknown.append("unknown_module:" + _hash(module))
            for node_id in matches:
                add("exact_module", node_id, module, len(matches) > 1)
        for node_id in query.node_ids:
            if node_id not in nodes:
                unknown.append("unknown_node:" + _hash(node_id))
            else:
                add("exact_node", node_id, node_id)
        for node_id in query.architecture_node_ids:
            if node_id not in nodes:
                unknown.append("unknown_architecture_node:" + _hash(node_id))
            else:
                add("architecture_endpoint", node_id, node_id)
        for symbol in query.symbol_names:
            matches = by_symbol.get(symbol, [])
            if not matches:
                unknown.append("unknown_symbol:" + _hash(symbol))
            for node_id in matches:
                add("exact_symbol", node_id, symbol, len(matches) > 1)
        for term in query.normalized_terms:
            for node_id in sorted(set(lexical.get(term, []))):
                add("lexical", node_id, term, len(set(lexical.get(term, []))) > 1)
        ordered_seeds = tuple(sorted(seeds.values()))
        adjacency: dict[str, list[tuple[str, str]]] = defaultdict(list)
        allowed = set(policy.allowed_edge_kinds)
        for edge in graph.edges:
            if edge.kind in allowed:
                adjacency[edge.source].append((edge.target, edge.kind.value + ":out"))
                adjacency[edge.target].append((edge.source, edge.kind.value + ":in"))
        for value in adjacency.values():
            value.sort()
        distances: dict[str, int] = {}
        paths: dict[str, tuple[str, ...]] = {}
        contributors: dict[str, set[str]] = defaultdict(set)
        alternatives: dict[str, int] = defaultdict(int)
        queue: deque[tuple[str, int, tuple[str, ...], str]] = deque()
        for seed in ordered_seeds:
            queue.append((seed.node_id, 0, (), seed.seed_id))
        while queue:
            node_id, distance, route, seed_id = queue.popleft()
            if distance > policy.max_depth:
                continue
            previous = distances.get(node_id)
            if previous is not None and distance > previous:
                continue
            contributors[node_id].add(seed_id)
            if previous is None or distance < previous or route < paths[node_id]:
                distances[node_id], paths[node_id], alternatives[node_id] = distance, route, 1
            elif distance == previous:
                alternatives[node_id] += 1
            if distance < policy.max_depth:
                for target, relation in adjacency.get(node_id, []):
                    queue.append((target, distance + 1, route + (relation,), seed_id))
        ranked: list[tuple[int, int, int, str, str, tuple[ScoreComponent, ...]]] = []
        policy_exclusions: dict[str, str] = {}
        seed_by_id = {s.seed_id: s for s in ordered_seeds}
        for node_id, distance in distances.items():
            node = nodes[node_id]
            if node.kind == NodeKind.EXTERNAL_MODULE and not policy.include_external:
                policy_exclusions[node_id] = "external_disabled"
            path = (
                node.file.path
                if node.file
                else node.owner_path or (node.symbol.path if node.symbol else None)
            )
            if path and not policy.include_tests and (path.startswith("tests/") or "/test" in path):
                policy_exclusions[node_id] = "tests_disabled"
            elif (
                path
                and not policy.include_generated
                and ("/generated/" in "/" + path or path.endswith("_generated.py"))
            ):
                policy_exclusions[node_id] = "generated_disabled"
            elif path and any(fnmatchcase(path, p) for p in policy.exclude_patterns):
                policy_exclusions[node_id] = "exclude_pattern"
            elif (
                path
                and policy.include_patterns
                and not any(fnmatchcase(path, p) for p in policy.include_patterns)
            ):
                policy_exclusions[node_id] = "outside_include_patterns"
            if distance == 0:
                components = [
                    ScoreComponent(seed_by_id[s].seed_type, seed_by_id[s].base_score)
                    for s in sorted(contributors[node_id])
                ]
            else:
                components = [
                    ScoreComponent(
                        "graph_seed_proximity",
                        max(seed_by_id[s].base_score for s in contributors[node_id]) // 10,
                    )
                ]
            components.append(ScoreComponent("graph_distance_decay", -100 * distance))
            if distance:
                relation = paths[node_id][0].replace(":", "_")
                components.append(ScoreComponent("relationship_" + relation, 120))
            evidence_types = {seed_by_id[s].seed_type for s in contributors[node_id]}
            if len(evidence_types) > 1:
                components.append(
                    ScoreComponent("independent_evidence_bonus", 50 * (len(evidence_types) - 1))
                )
            if any(seed_by_id[s].ambiguous for s in contributors[node_id]):
                components.append(ScoreComponent("ambiguity_penalty", -150))
            combined: dict[str, int] = defaultdict(int)
            for component in components:
                combined[component.name] += component.value
            final = tuple(sorted(ScoreComponent(k, v) for k, v in combined.items()))
            total = sum(x.value for x in final)
            ranked.append((-total, distance, KIND_PRIORITY[node.kind], node_id, path or "", final))
        ranked.sort()
        candidates: list[RetrievalCandidate] = []
        files: set[str] = set()
        ranges: dict[str, list[tuple[int, int]]] = defaultdict(list)
        per_file: dict[str, int] = defaultdict(int)
        symbols = excerpts = lines = byte_count = 0
        for rank, row in enumerate(ranked[: policy.max_manifest_candidates], 1):
            _, distance, _, node_id, path, row_components = row
            node = nodes[node_id]
            file = next((f for f in snapshot.files if f.path == path), None)
            start = (
                max(1, node.symbol.start_line - policy.context_before)
                if node.symbol
                else (1 if file and file.line_count else None)
            )
            end = (
                min(file.line_count, node.symbol.end_line + policy.context_after)
                if node.symbol and file
                else (file.line_count if file and file.line_count else None)
            )
            cost_lines = end - start + 1 if start is not None and end is not None else 0
            if path and start is not None and end is not None:
                covered = {
                    line
                    for old_start, old_end in ranges[path]
                    for line in range(old_start, old_end + 1)
                }
                incremental_lines = sum(line not in covered for line in range(start, end + 1))
            else:
                incremental_lines = 0
            cost_lines = incremental_lines
            cost_bytes = file.byte_size if file and cost_lines and path not in files else 0
            is_symbol = node.kind in {NodeKind.CLASS, NodeKind.FUNCTION, NodeKind.ASYNC_FUNCTION}
            new_file = bool(path and path not in files)
            reason = ""
            state = SelectionState.SELECTED
            if node_id in policy_exclusions:
                state, reason = SelectionState.EXCLUDED, policy_exclusions[node_id]
            elif not path or not file or start is None or end is None:
                state, reason = SelectionState.EXCLUDED, "no_source_range"
            elif not cost_lines:
                state, reason = SelectionState.EXCLUDED, "duplicate_range"
            elif excerpts + 1 > policy.max_excerpts:
                state, reason = SelectionState.EXCLUDED, "max_excerpts"
            elif path and per_file[path] + 1 > policy.per_file_excerpt_limit:
                state, reason = SelectionState.EXCLUDED, "per_file_excerpt_limit"
            elif new_file and len(files) + 1 > policy.max_files:
                state, reason = SelectionState.EXCLUDED, "max_files"
            elif is_symbol and symbols + 1 > policy.max_symbols:
                state, reason = SelectionState.EXCLUDED, "max_symbols"
            elif lines + cost_lines > policy.max_lines:
                state, reason = SelectionState.EXCLUDED, "max_lines"
            elif byte_count + cost_bytes > policy.max_source_bytes:
                state, reason = SelectionState.EXCLUDED, "max_bytes"
            if state == SelectionState.SELECTED:
                files.add(path)
                ranges[path].append((start, end))  # type: ignore[arg-type]
                per_file[path] += 1
                symbols += int(is_symbol)
                excerpts += 1
                lines += cost_lines
                byte_count += cost_bytes
                reason = "within_budget"
            candidates.append(
                RetrievalCandidate(
                    rank,
                    node_id,
                    node.kind,
                    path or None,
                    node.module_name,
                    node.symbol.qualified_name if node.symbol else None,
                    start,
                    end,
                    sum(x.value for x in row_components),
                    row_components,
                    distance,
                    tuple(contributors[node_id]),
                    paths[node_id],
                    max(1, alternatives[node_id]),
                    state,
                    reason,
                    cost_lines if state == SelectionState.SELECTED else 0,
                    cost_bytes if state == SelectionState.SELECTED else 0,
                )
            )
        budget = BudgetSummary(len(files), symbols, excerpts, lines, byte_count)
        manifest = RetrievalManifest.create(
            query.query_fingerprint,
            snapshot.repository_fingerprint,
            graph.graph_fingerprint,
            policy,
            ordered_seeds,
            tuple(candidates),
            budget,
            not graph.input_partial,
            tuple(unknown),
        )
        if output:
            self.artifacts.write_manifest(manifest, output)
        return RetrievalResult(manifest)


class BuildContextBundle:
    def __init__(self, reader: SourceExcerptReaderPort, artifacts: ContextArtifactPort) -> None:
        self.reader, self.artifacts = reader, artifacts

    def execute(
        self,
        repository: Path,
        snapshot: RepositorySnapshot,
        manifest: RetrievalManifest,
        output: Path,
    ) -> ContextBundle:
        if manifest.snapshot_fingerprint != snapshot.repository_fingerprint:
            raise ValueError("manifest and snapshot fingerprint mismatch")
        ranges: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for candidate in manifest.candidates:
            if candidate.selection_state == SelectionState.SELECTED and candidate.path:
                assert candidate.line_start is not None and candidate.line_end is not None
                ranges[candidate.path].append((candidate.line_start, candidate.line_end))
        merged: list[tuple[str, int, int]] = []
        for path in sorted(ranges):
            for start, end in sorted(ranges[path]):
                if merged and merged[-1][0] == path and start <= merged[-1][2] + 1:
                    old = merged.pop()
                    merged.append((path, old[1], max(old[2], end)))
                else:
                    merged.append((path, start, end))
        excerpts = tuple(self.reader.read(repository, snapshot, *item) for item in merged)
        bundle = ContextBundle.create(manifest, excerpts)
        if (
            bundle.total_lines > manifest.policy.max_lines
            or bundle.total_bytes > manifest.policy.max_source_bytes
        ):
            raise ValueError("actual bundle exceeds manifest budget")
        self.artifacts.write_bundle(bundle, output)
        return bundle


def _decimal(numerator: int, denominator: int) -> str:
    return str(
        (Decimal(numerator) / Decimal(denominator)).quantize(
            Decimal("0.000000"), rounding=ROUND_HALF_EVEN
        )
    )


class EvaluateRetrieval:
    def __init__(self, artifacts: ContextArtifactPort) -> None:
        self.artifacts = artifacts

    def execute(
        self, manifest: RetrievalManifest, labels: RelevanceLabels, output: Path | None = None
    ) -> RetrievalEvaluation:
        ranked = [c.node_id for c in manifest.candidates]
        relevant = set(labels.relevant_node_ids)
        known = set(ranked)
        missing = tuple(sorted(relevant - known))
        metrics: list[Metric] = []
        first = next((i for i, value in enumerate(ranked, 1) if value in relevant), 0)
        metrics.append(
            Metric("MRR", int(bool(first)), first or 1, _decimal(1, first) if first else "0.000000")
        )
        for k in (1, 3, 5, 10):
            selected = ranked[:k]
            hits = len(set(selected) & relevant)
            metrics.append(Metric(f"Hit@{k}", int(hits > 0), 1, _decimal(int(hits > 0), 1)))
            metrics.append(
                Metric(
                    f"Precision@{k}",
                    hits,
                    max(1, len(selected)),
                    _decimal(hits, max(1, len(selected))),
                )
            )
            metrics.append(
                Metric(
                    f"Recall@{k}",
                    hits,
                    max(1, len(relevant)),
                    _decimal(hits, max(1, len(relevant))),
                )
            )
        result = RetrievalEvaluation.create(manifest, labels, missing, tuple(metrics))
        if output:
            self.artifacts.write_evaluation(result, output)
        return result
