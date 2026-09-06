"""Provider-neutral loading, evaluation and independent persistence contracts."""

from pathlib import Path
from typing import Protocol

from archguard.domain.architecture_profile import ArchitectureProfile
from archguard.domain.architecture_report import ArchitectureReport
from archguard.domain.graph import RepositoryGraph
from archguard.domain.models import ArtifactReference


class ArchitectureProfileLoaderPort(Protocol):
    def load(self, source: Path) -> ArchitectureProfile: ...


class ArchitectureProfileReaderPort(Protocol):
    def read(self, source: Path, expected_sha256: str | None = None) -> ArchitectureProfile: ...


class ArchitectureProfileWriterPort(Protocol):
    def validate_destination(
        self,
        destination: Path,
        protected_root: Path | None = None,
        sources: tuple[Path, ...] = (),
    ) -> None: ...

    def write(self, profile: ArchitectureProfile, destination: Path) -> ArtifactReference: ...


class ArchitectureConstraintEvaluatorPort(Protocol):
    def evaluate(
        self, graph: RepositoryGraph, profile: ArchitectureProfile
    ) -> ArchitectureReport: ...


class ArchitectureReportReaderPort(Protocol):
    def read(self, source: Path, expected_sha256: str | None = None) -> ArchitectureReport: ...


class ArchitectureReportWriterPort(Protocol):
    def validate_destination(
        self,
        destination: Path,
        protected_root: Path | None = None,
        sources: tuple[Path, ...] = (),
    ) -> None: ...

    def write(self, report: ArchitectureReport, destination: Path) -> ArtifactReference: ...
