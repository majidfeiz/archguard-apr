from dataclasses import dataclass
from pathlib import Path

from archguard.application.ports.repository import (
    AnalysisArtifactReaderPort,
    AnalysisArtifactWriterPort,
    RepositoryAnalyzerPort,
)
from archguard.domain.models import ArtifactReference
from archguard.domain.repository import AnalysisOptions, RepositorySnapshot


class UnsafePathError(ValueError):
    """A requested path violates local access policy."""


class AnalysisError(RuntimeError):
    """Analysis stopped before a snapshot could be produced."""


@dataclass(frozen=True)
class AnalysisResult:
    snapshot: RepositorySnapshot
    artifact: ArtifactReference | None = None


class AnalyzeRepository:
    def __init__(
        self, analyzer: RepositoryAnalyzerPort, writer: AnalysisArtifactWriterPort
    ) -> None:
        self.analyzer = analyzer
        self.writer = writer

    def execute(
        self,
        repository: Path,
        options: AnalysisOptions | None = None,
        output: Path | None = None,
    ) -> AnalysisResult:
        if not str(repository).strip():
            raise ValueError("repository root is required")
        if output is not None:
            self.writer.validate_destination(repository, output)
        snapshot = self.analyzer.analyze(repository, options or AnalysisOptions())
        artifact = self.writer.write(snapshot, output) if output is not None else None
        return AnalysisResult(snapshot, artifact)


class InspectRepository:
    def __init__(self, reader: AnalysisArtifactReaderPort) -> None:
        self.reader = reader

    def execute(self, source: Path, expected_sha256: str | None = None) -> RepositorySnapshot:
        return self.reader.read(source, expected_sha256)
