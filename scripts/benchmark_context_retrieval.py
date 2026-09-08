"""Fixed engineering workload; observed timings never enter canonical identities."""

import json
import tempfile
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from typing import Any

from archguard.application.services.context import (
    BuildContextBundle,
    CompileRetrievalQuery,
    EvaluateRetrieval,
    RetrieveRepositoryContext,
)
from archguard.application.services.graph_builder import DeterministicGraphBuilder
from archguard.domain.canonical import canonical_json
from archguard.domain.context import RelevanceLabels, RetrievalPolicy
from archguard.domain.graph import GraphBuildOptions
from archguard.domain.repository import AnalysisOptions
from archguard.infrastructure.context_artifacts import LocalContextArtifacts
from archguard.infrastructure.repository_analyzer import LocalRepositoryAnalyzer
from archguard.infrastructure.source_excerpt_reader import LocalSourceExcerptReader


def timed(call: Any) -> tuple[Any, float]:
    started = perf_counter()
    return call(), perf_counter() - started


with tempfile.TemporaryDirectory(prefix="archguard-context-workload-") as temporary:
    workspace = Path(temporary)
    root = workspace / "repository"
    source = root / "src/workload"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("")
    for index in range(100):
        dependency = f"from .module_{index - 1:03d} import value\n" if index else ""
        (source / f"module_{index:03d}.py").write_text(dependency + f"value = {index}\n")
    snapshot = LocalRepositoryAnalyzer().analyze(root, AnalysisOptions(source_roots=("src",)))
    graph = DeterministicGraphBuilder().build(snapshot, GraphBuildOptions())
    query, compile_seconds = timed(
        lambda: CompileRetrievalQuery().execute(
            "guardrail", "module 050 dependency failure", modules=("workload.module_050",)
        )
    )
    artifacts = LocalContextArtifacts()
    policy = RetrievalPolicy(
        max_depth=2, max_files=10, max_symbols=20, max_lines=100, max_source_bytes=20_000
    )
    manifest, retrieval_seconds = timed(
        lambda: (
            RetrieveRepositoryContext(artifacts).execute(snapshot, graph, query, policy).manifest
        )
    )
    manifest_raw, manifest_seconds = timed(lambda: canonical_json(asdict(manifest)))
    bundle, extraction_seconds = timed(
        lambda: BuildContextBundle(LocalSourceExcerptReader(), artifacts).execute(
            root, snapshot, manifest, workspace / "bundle.json"
        )
    )
    bundle_raw, bundle_seconds = timed(lambda: canonical_json(asdict(bundle)))
    labels = RelevanceLabels.create(("module:workload.module_050",))
    evaluation, evaluation_seconds = timed(
        lambda: EvaluateRetrieval(artifacts).execute(manifest, labels)
    )
    print(
        json.dumps(
            {
                "graph_nodes": len(graph.nodes),
                "candidates": len(manifest.candidates),
                "selected": manifest.budget.selected_excerpts,
                "source_lines": bundle.total_lines,
                "source_bytes": bundle.total_bytes,
                "manifest_bytes": len(manifest_raw),
                "bundle_bytes": len(bundle_raw),
                "environment": "local-python-3.12-or-3.13",
                "seconds": {
                    "query_compilation": compile_seconds,
                    "seed_expansion_scoring_budget": retrieval_seconds,
                    "source_extraction": extraction_seconds,
                    "manifest_serialization": manifest_seconds,
                    "bundle_serialization": bundle_seconds,
                    "evaluation": evaluation_seconds,
                },
                "evaluation_fingerprint": evaluation.evaluation_fingerprint,
            },
            sort_keys=True,
        )
    )
