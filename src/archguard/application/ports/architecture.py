from pathlib import Path
from typing import Protocol

from archguard.domain.models import ArtifactReference, ValidationSummary


class ArchitectureAnalyzerPort(Protocol):
    def analyze(self, repository: Path) -> tuple[ArtifactReference, ValidationSummary]:
        """Return a profile artifact and existing dependency violations; read only."""
        ...


class ArchitectureValidatorPort(Protocol):
    def validate(self, before: ArtifactReference, candidate_worktree: Path) -> ValidationSummary:
        """Compare the baseline profile to a candidate worktree without modifying either."""
        ...
