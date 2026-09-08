"""Deterministic source-free self-hosting retrieval guardrail."""

import json
from dataclasses import asdict
from pathlib import Path

from archguard.application.services.context import CompileRetrievalQuery, RetrieveRepositoryContext
from archguard.application.services.graph_builder import DeterministicGraphBuilder
from archguard.domain.canonical import canonical_json
from archguard.domain.context import RetrievalPolicy
from archguard.domain.graph import GraphBuildOptions
from archguard.domain.repository import AnalysisOptions
from archguard.infrastructure.context_artifacts import LocalContextArtifacts
from archguard.infrastructure.repository_analyzer import LocalRepositoryAnalyzer

root = Path.cwd()
snapshot = LocalRepositoryAnalyzer().analyze(
    root,
    AnalysisOptions(
        source_roots=("src", "tests"),
        excluded_patterns=("examples/*", "tests/__init__.py"),
    ),
)
graph = DeterministicGraphBuilder().build(snapshot, GraphBuildOptions())
query = CompileRetrievalQuery().execute(
    "phase-6-self",
    "Architecture patch validation fails to clean up an isolated Git worktree.",
    paths=(
        "src/archguard/application/services/patch_validation.py",
        "src/archguard/infrastructure/git_worktree.py",
    ),
)
policy = RetrievalPolicy(
    max_depth=2, max_files=12, max_symbols=30, max_lines=500, max_source_bytes=50_000
)
service = RetrieveRepositoryContext(LocalContextArtifacts())
first = service.execute(snapshot, graph, query, policy).manifest
second = service.execute(snapshot, graph, query, policy).manifest
assert canonical_json(asdict(first)) == canonical_json(asdict(second))
top = first.candidates[:50]
assert first.complete and first.budget.consumed_lines <= policy.max_lines
assert any("patch_validation.py" in (candidate.path or "") for candidate in top)
assert any("git_worktree.py" in (candidate.path or "") for candidate in first.candidates)
print(
    json.dumps(
        {
            "manifest_fingerprint": first.manifest_fingerprint,
            "candidate_count": len(first.candidates),
            "selected_count": first.budget.selected_excerpts,
            "top_paths": [candidate.path for candidate in top[:10]],
        },
        sort_keys=True,
    )
)
