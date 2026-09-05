from pathlib import Path
from typing import Protocol

from archguard.domain.models import ArtifactReference
from archguard.domain.repository import AnalysisOptions, RepositorySnapshot


class RepositoryAnalyzerPort(Protocol):
    def analyze(self, repository: Path, options: AnalysisOptions) -> RepositorySnapshot:
        """Read source without execution or persistence; return a canonical snapshot."""
        ...


class AnalysisArtifactWriterPort(Protocol):
    def validate_destination(self, repository: Path, destination: Path) -> None:
        """Reject traversal, symlink destinations and writes inside the target before analysis."""
        ...

    def write(self, snapshot: RepositorySnapshot, destination: Path) -> ArtifactReference:
        """Atomically persist canonical bytes; return a relative reference with SHA-256."""
        ...


class AnalysisArtifactReaderPort(Protocol):
    def read(self, source: Path, expected_sha256: str | None = None) -> RepositorySnapshot:
        """Validate schema, canonical invariants, fingerprint and optional raw artifact digest."""
        ...
