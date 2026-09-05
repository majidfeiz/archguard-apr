"""Replaceable local artifact persistence; no writes to analyzed roots."""

import hashlib
from pathlib import Path

from archguard.application.services.repository import UnsafePathError
from archguard.domain.enums import ArtifactKind
from archguard.domain.models import ArtifactReference
from archguard.domain.repository import RepositorySnapshot
from archguard.infrastructure.artifact_io import atomic_write, read_artifact
from archguard.infrastructure.artifact_io import destination_path as destination_path
from archguard.infrastructure.repository_analyzer import validate_root
from archguard.infrastructure.repository_codec import canonical_snapshot, decode_snapshot

MAX_ARTIFACT_BYTES = 64 * 1024 * 1024


class LocalAnalysisArtifacts:
    def validate_destination(self, repository: Path, destination: Path) -> None:
        root = validate_root(repository)
        target = destination_path(destination)
        if target.is_relative_to(root):
            raise UnsafePathError("analysis output must be outside the analyzed repository")

    def write(self, snapshot: RepositorySnapshot, destination: Path) -> ArtifactReference:
        target = destination_path(destination)
        raw = canonical_snapshot(snapshot)
        atomic_write(target, raw)
        return ArtifactReference(
            target.name, ArtifactKind.ANALYSIS, hashlib.sha256(raw).hexdigest()
        )

    def read(self, source: Path, expected_sha256: str | None = None) -> RepositorySnapshot:
        return decode_snapshot(read_artifact(source, expected_sha256, MAX_ARTIFACT_BYTES))
