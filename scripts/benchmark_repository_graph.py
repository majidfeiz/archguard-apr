"""Engineering guardrail, not a scientific benchmark or CI timing assertion."""

import json
import tempfile
from pathlib import Path
from time import perf_counter

from archguard.application.services.graph_builder import DeterministicGraphBuilder
from archguard.domain.graph import GraphBuildOptions
from archguard.domain.repository import AnalysisOptions
from archguard.infrastructure.graph_artifacts import canonical_graph
from archguard.infrastructure.repository_analyzer import LocalRepositoryAnalyzer


def main() -> None:
    # Fixture preparation and AST analysis are deliberately outside graph timing.
    with tempfile.TemporaryDirectory(prefix="archguard-graph-benchmark-") as directory:
        root = Path(directory)
        for index in range(500):
            source = (
                f"import module_{(index + 1) % 500:03d}\n"
                f"import module_{(index + 2) % 500:03d}\n"
                + "".join(f"def function_{item}(): pass\n" for item in range(4))
            )
            (root / f"module_{index:03d}.py").write_text(source, encoding="utf-8")
        snapshot = LocalRepositoryAnalyzer().analyze(root, AnalysisOptions())
    started = perf_counter()
    graph = DeterministicGraphBuilder().build(snapshot, GraphBuildOptions())
    duration = perf_counter() - started
    print(
        json.dumps(
            {
                "construction_seconds": round(duration, 6),
                "files": graph.summary.file_nodes,
                "modules": graph.summary.module_nodes,
                "symbols": graph.summary.function_nodes,
                "imports": graph.summary.import_edges,
                "nodes": graph.summary.total_nodes,
                "edges": graph.summary.total_edges,
                "artifact_bytes": len(canonical_graph(graph)),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
