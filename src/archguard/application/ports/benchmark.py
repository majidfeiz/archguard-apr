"""Trusted benchmark evaluation boundary, separate from repair-agent ports."""

from pathlib import Path
from typing import Protocol

from archguard.domain.benchmark import BenchmarkTask
from archguard.domain.execution import ExecutionEvidence, ExecutionPlan
from archguard.domain.repair import PatchCandidate


class TrustedBenchmarkEvaluatorPort(Protocol):
    """Evaluate a candidate without returning tests, source, or gold material."""

    def evaluate(
        self,
        task: BenchmarkTask,
        candidate: PatchCandidate,
        plan: ExecutionPlan,
        agent_workspace: Path,
        evaluator_workspace: Path,
        quarantined_workspace: Path,
    ) -> ExecutionEvidence: ...


class BenchmarkAcquisitionPort(Protocol):
    """Acquire immutable metadata into a caller-selected untracked cache."""

    def acquire(self, benchmark_id: str, revision: str, destination: Path) -> str: ...
