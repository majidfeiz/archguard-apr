from pathlib import Path
from typing import Protocol

from archguard.domain.graph import GraphBuildOptions, RepositoryGraph
from archguard.domain.models import ArtifactReference
from archguard.domain.repository import RepositorySnapshot


class RepositoryGraphBuilderPort(Protocol):
    def build(self, snapshot: RepositorySnapshot, options: GraphBuildOptions) -> RepositoryGraph:
        """Construct from validated in-memory metadata only; never read source or persist."""
        ...


class GraphArtifactWriterPort(Protocol):
    def validate_destination(
        self, destination: Path, protected_root: Path | None = None, source: Path | None = None
    ) -> None:
        """Reject unsafe destinations and writes within a known protected source root."""
        ...

    def write(self, graph: RepositoryGraph, destination: Path) -> ArtifactReference:
        """Atomically persist canonical graph bytes and report their SHA-256."""
        ...


class GraphArtifactReaderPort(Protocol):
    def read(self, source: Path, expected_sha256: str | None = None) -> RepositoryGraph:
        """Read bounded untrusted JSON; validate invariants and optional artifact hash."""
        ...
