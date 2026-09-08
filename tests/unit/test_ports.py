from pathlib import Path

import pytest

from archguard.application.ports.context import (
    ContextArtifactPort,
    RelevanceLabelPort,
    SourceExcerptReaderPort,
)
from archguard.application.ports.execution import ExecutionRunnerPort
from archguard.application.ports.patch_validation import (
    CandidatePatchInspectorPort,
    CandidateWorkspacePort,
    PatchValidationArtifactPort,
    RepositoryStatePort,
)
from archguard.application.ports.repair import RepairProviderPort
from archguard.domain.enums import ArtifactKind
from archguard.domain.models import ArtifactReference, ExecutionResult
from archguard.infrastructure.context_artifacts import LocalContextArtifacts, LocalRelevanceLabels
from archguard.infrastructure.git_worktree import GitCandidateWorkspace, GitRepositoryState
from archguard.infrastructure.patch_artifacts import LocalPatchValidationArtifacts
from archguard.infrastructure.patch_inspector import UnifiedDiffInspector
from archguard.infrastructure.source_excerpt_reader import LocalSourceExcerptReader

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
    artifacts: ContextArtifactPort = LocalContextArtifacts()
    labels: RelevanceLabelPort = LocalRelevanceLabels()
    reader: SourceExcerptReaderPort = LocalSourceExcerptReader()
    assert artifacts and labels and reader


def test_patch_validation_adapters_satisfy_narrow_ports() -> None:
    inspector: CandidatePatchInspectorPort = UnifiedDiffInspector()
    states: RepositoryStatePort = GitRepositoryState()
    workspaces: CandidateWorkspacePort = GitCandidateWorkspace()
    artifacts: PatchValidationArtifactPort = LocalPatchValidationArtifacts()
    assert inspector and states and workspaces and artifacts
