from pathlib import Path

import pytest

from archguard.application.ports.architecture import (
    ArchitectureAnalyzerPort,
    ArchitectureValidatorPort,
)
from archguard.application.ports.execution import ExecutionRunnerPort
from archguard.application.ports.repair import RepairProviderPort
from archguard.application.ports.repository import RepositoryAnalyzerPort
from archguard.domain.enums import ArtifactKind
from archguard.domain.models import ArtifactReference, ExecutionResult, ValidationSummary

pytestmark = pytest.mark.unit


class ReadOnlyAnalysis:
    def analyze(self, repository: Path) -> ArtifactReference:
        assert repository.is_dir()
        return ArtifactReference("analysis.json", ArtifactKind.ANALYSIS)


class ProfileAnalysis:
    def analyze(self, repository: Path) -> tuple[ArtifactReference, ValidationSummary]:
        assert repository.is_dir()
        return ArtifactReference(
            "profile.json", ArtifactKind.ARCHITECTURE_PROFILE
        ), ValidationSummary()


class Validator:
    def validate(self, before: ArtifactReference, candidate_worktree: Path) -> ValidationSummary:
        assert before.kind is ArtifactKind.ARCHITECTURE_PROFILE
        assert candidate_worktree.is_dir()
        return ValidationSummary()


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
    repository: RepositoryAnalyzerPort = ReadOnlyAnalysis()
    architecture: ArchitectureAnalyzerPort = ProfileAnalysis()
    validator: ArchitectureValidatorPort = Validator()
    runner: ExecutionRunnerPort = ExecutionFake()
    repair: RepairProviderPort = RepairFake()
    analysis = repository.analyze(tmp_path)
    profile, existing = architecture.analyze(tmp_path)
    assert existing.passed and validator.validate(profile, tmp_path).passed
    assert repair.propose(analysis, "reproducible failure").kind is ArtifactKind.CANDIDATE_PATCH
    assert runner.run(("fixture",), tmp_path, 1).exit_code == 0
    assert not list(tmp_path.iterdir())
