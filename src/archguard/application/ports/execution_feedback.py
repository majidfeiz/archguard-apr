"""Narrow ports for trusted execution plans, sandboxing and semantic artifacts."""

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from archguard.domain.execution import ExecutionEvidence, ExecutionPlan


class ExecutionPlanPort(Protocol):
    def load(self, source: Path) -> ExecutionPlan: ...


class SandboxExecutionPort(Protocol):
    def execute(
        self, plan: ExecutionPlan, workspace: Path, allowed_environment: Mapping[str, str]
    ) -> ExecutionEvidence: ...


class ExecutionEvidenceArtifactPort(Protocol):
    def write(self, evidence: ExecutionEvidence, destination: Path) -> None: ...
