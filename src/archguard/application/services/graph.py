from dataclasses import dataclass
from pathlib import Path

from archguard.application.ports.graph import (
    GraphArtifactReaderPort,
    GraphArtifactWriterPort,
    RepositoryGraphBuilderPort,
)
from archguard.application.ports.repository import AnalysisArtifactReaderPort
from archguard.domain.graph import GraphBuildOptions, RepositoryGraph
from archguard.domain.models import ArtifactReference


@dataclass(frozen=True)
class GraphBuildResult:
    graph: RepositoryGraph
    artifact: ArtifactReference


class BuildRepositoryGraph:
    def __init__(
        self,
        snapshots: AnalysisArtifactReaderPort,
        builder: RepositoryGraphBuilderPort,
        writer: GraphArtifactWriterPort,
    ) -> None:
        self.snapshots, self.builder, self.writer = snapshots, builder, writer

    def execute(
        self,
        source: Path,
        output: Path,
        options: GraphBuildOptions | None = None,
        protected_root: Path | None = None,
    ) -> GraphBuildResult:
        if source == output:
            raise ValueError("graph output must not replace its input snapshot")
        self.writer.validate_destination(output, protected_root, source)
        snapshot = self.snapshots.read(source)
        graph = self.builder.build(snapshot, options or GraphBuildOptions())
        return GraphBuildResult(graph, self.writer.write(graph, output))


class InspectRepositoryGraph:
    def __init__(self, reader: GraphArtifactReaderPort) -> None:
        self.reader = reader

    def execute(self, source: Path, expected_sha256: str | None = None) -> RepositoryGraph:
        return self.reader.read(source, expected_sha256)
