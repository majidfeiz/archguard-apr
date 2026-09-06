from pathlib import Path

import pytest

from archguard.application.ports.execution import ExecutionRunnerPort
from archguard.application.ports.repair import RepairProviderPort
from archguard.domain.enums import ArtifactKind
from archguard.domain.models import ArtifactReference, ExecutionResult

pytestmark = pytest.mark.unit


class ExecutionFake:
    def run(
        self, command: tuple[str, ...], workspace: Path, timeout_seconds: float
    ) -> ExecutionResult:
        assert command and workspace.is_dir() and timeout_seconds > 0
        return ExecutionResult("fixture output", "", 0, 0)


class RepairFake:
    def propose(self, analysis: ArtifactReference, problem: str) -> ArtifactReference:
        assert analysis.kind is ArtifactKind.ANALYSIS and problem
        return ArtifactReference("candidate.diff", ArtifactKind.CANDIDATE_PATCH)


def test_provider_neutral_structural_contracts(tmp_path: Path) -> None:
    """Third-party-shaped fakes satisfy ports without inheriting framework classes."""
    runner: ExecutionRunnerPort = ExecutionFake()
    repair: RepairProviderPort = RepairFake()
    analysis = ArtifactReference("analysis.json", ArtifactKind.ANALYSIS)
    assert repair.propose(analysis, "reproducible failure").kind is ArtifactKind.CANDIDATE_PATCH
    assert runner.run(("fixture",), tmp_path, 1).exit_code == 0
    assert not list(tmp_path.iterdir())
