"""Narrow external boundaries for context artifacts and source access."""

from pathlib import Path
from typing import Protocol

from archguard.domain.context import (
    CompiledRetrievalQuery,
    ContextBundle,
    RelevanceLabels,
    RetrievalEvaluation,
    RetrievalManifest,
    SourceExcerpt,
)
from archguard.domain.models import ArtifactReference
from archguard.domain.repository import RepositorySnapshot


class ContextArtifactPort(Protocol):
    def write_query(
        self, value: CompiledRetrievalQuery, destination: Path
    ) -> ArtifactReference: ...
    def read_query(
        self, source: Path, expected_sha256: str | None = None
    ) -> CompiledRetrievalQuery: ...
    def write_manifest(self, value: RetrievalManifest, destination: Path) -> ArtifactReference: ...
    def read_manifest(
        self, source: Path, expected_sha256: str | None = None
    ) -> RetrievalManifest: ...
    def write_bundle(self, value: ContextBundle, destination: Path) -> ArtifactReference: ...
    def read_bundle(self, source: Path, expected_sha256: str | None = None) -> ContextBundle: ...
    def write_evaluation(
        self, value: RetrievalEvaluation, destination: Path
    ) -> ArtifactReference: ...
    def read_evaluation(
        self, source: Path, expected_sha256: str | None = None
    ) -> RetrievalEvaluation: ...


class RelevanceLabelPort(Protocol):
    def load(self, source: Path) -> RelevanceLabels: ...


class SourceExcerptReaderPort(Protocol):
    def read(
        self,
        repository: Path,
        snapshot: RepositorySnapshot,
        path: str,
        line_start: int,
        line_end: int,
    ) -> SourceExcerpt: ...
