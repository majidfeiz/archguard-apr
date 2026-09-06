"""Deterministic engineering workload; timings are not scientific evidence."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from archguard.application.services.constraint_engine import (
    DeterministicConstraintEvaluator,
    assign_components,
)
from archguard.application.services.graph_builder import DeterministicGraphBuilder
from archguard.domain.architecture_profile import (
    ArchitectureComponent,
    ArchitectureProfile,
    ForbidDependency,
    ModuleSelector,
)
from archguard.domain.graph import GraphBuildOptions
from archguard.domain.repository import AnalysisOptions
from archguard.infrastructure.architecture_reports import canonical_report
from archguard.infrastructure.repository_analyzer import LocalRepositoryAnalyzer


def main() -> None:
    # No randomness: each of 500 modules imports its next two ring neighbors.
    with TemporaryDirectory(prefix="archguard-constraint-", dir="/tmp") as directory:
        root = Path(directory)
        for i in range(500):
            (root / f"m{i}.py").write_text(
                f"import m{(i + 1) % 500}\nimport m{(i + 2) % 500}\n", encoding="utf-8"
            )
        snapshot = LocalRepositoryAnalyzer().analyze(root, AnalysisOptions())
    graph = DeterministicGraphBuilder().build(snapshot, GraphBuildOptions())
    profile = ArchitectureProfile.create(
        "guardrail",
        "Deterministic engineering guardrail",
        tuple(
            ArchitectureComponent(
                f"group-{group}",
                tuple(
                    ModuleSelector("module_exact", f"m{i}")
                    for i in range(group * 100, (group + 1) * 100)
                ),
            )
            for group in range(5)
        ),
        tuple(
            ForbidDependency(id=f"rule-{i}", source=f"group-{i % 5}", target=f"group-{(i + 1) % 5}")
            for i in range(100)
        ),
    )
    started = perf_counter()
    assign_components(graph, profile)
    assignment = perf_counter() - started
    started = perf_counter()
    report = DeterministicConstraintEvaluator().evaluate(graph, profile)
    duration = perf_counter() - started
    print(
        json.dumps(
            {
                "workload_version": "1",
                "seed": None,
                "randomness": "none",
                "modules": 500,
                "components": 5,
                "rules": 100,
                "import_occurrences": 1000,
                "assignment_seconds": round(assignment, 6),
                "evaluation_seconds": round(duration, 6),
                "evaluation_includes_assignment_validation_and_hashing": True,
                "violation_count": len(report.violations),
                "canonical_report_bytes": len(canonical_report(report)),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
