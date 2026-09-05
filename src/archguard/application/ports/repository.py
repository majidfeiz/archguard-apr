from pathlib import Path
from typing import Protocol

from archguard.domain.models import ArtifactReference


class RepositoryAnalyzerPort(Protocol):
    def analyze(self, repository: Path) -> ArtifactReference:
        """Read only; return a persisted analysis artifact, never mutate the repository."""
        ...
