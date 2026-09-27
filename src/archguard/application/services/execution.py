"""Provider-neutral orchestration for equivalent baseline/candidate sandbox runs."""

from collections.abc import Mapping
from pathlib import Path

from archguard.application.ports.execution_feedback import SandboxExecutionPort
from archguard.application.ports.patch_validation import CandidateWorkspacePort
from archguard.domain.execution import (
    ExecutionEvidence,
    ExecutionPlan,
    FunctionalDelta,
    compare_evidence,
)


class CompareFunctionalBehavior:
    def __init__(self, workspaces: CandidateWorkspacePort, sandbox: SandboxExecutionPort) -> None:
        self.workspaces = workspaces
        self.sandbox = sandbox

    def execute(
        self,
        repository: Path,
        baseline_commit: str,
        patch: bytes,
        plan: ExecutionPlan,
        environment: Mapping[str, str],
    ) -> tuple[ExecutionEvidence, ExecutionEvidence, FunctionalDelta]:
        with self.workspaces.workspace(repository, baseline_commit) as baseline_workspace:
            baseline = self.sandbox.execute(plan, baseline_workspace, environment)
        with self.workspaces.workspace(repository, baseline_commit) as candidate_workspace:
            if not self.workspaces.check_apply(candidate_workspace, patch):
                raise ValueError("candidate patch does not apply")
            if not self.workspaces.apply(candidate_workspace, patch):
                raise ValueError("candidate patch application failed")
            candidate = self.sandbox.execute(plan, candidate_workspace, environment)
        return baseline, candidate, compare_evidence(baseline, candidate, plan)
