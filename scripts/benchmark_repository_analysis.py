"""Optional 500-file engineering guardrail; not a scientific performance experiment."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from archguard.domain.repository import AnalysisOptions
from archguard.infrastructure.repository_analyzer import LocalRepositoryAnalyzer


def main() -> None:
    with TemporaryDirectory(prefix="archguard-guardrail-") as directory:
        root = Path(directory)
        for index in range(500):
            (root / f"module_{index:04d}.py").write_text(
                f"def value_{index}() -> int:\n    return {index}\n", encoding="utf-8"
            )
        started = perf_counter()
        snapshot = LocalRepositoryAnalyzer().analyze(root, AnalysisOptions())
        duration = perf_counter() - started
        assert snapshot.summary.parsed_files == 500
        print(
            json.dumps(
                {"files": 500, "duration_seconds": duration, "purpose": "engineering guardrail"}
            )
        )


if __name__ == "__main__":
    main()
