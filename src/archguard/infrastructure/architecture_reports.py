"""Separate canonical architecture report reader and writer adapter."""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from pydantic import TypeAdapter

from archguard.domain.architecture_report import ArchitectureReport
from archguard.domain.canonical import canonical_json
from archguard.domain.enums import ArtifactKind
from archguard.domain.models import ArtifactReference
from archguard.infrastructure.artifact_io import atomic_write, destination_path, read_artifact
from archguard.infrastructure.graph_artifacts import LocalGraphArtifacts
from archguard.infrastructure.json_codec import unique_object

MAX_REPORT_BYTES = 64 * 1024 * 1024


def canonical_report(report: ArchitectureReport) -> bytes:
    return canonical_json(asdict(report))


def decode_report(raw: bytes) -> ArchitectureReport:
    try:
        data = json.loads(raw, object_pairs_hook=unique_object)
        report = TypeAdapter(ArchitectureReport).validate_json(raw, strict=True)
        if json.loads(canonical_report(report)) != data:
            raise ValueError("noncanonical report shape")
        return report
    except (ValueError, TypeError, KeyError, RecursionError, AttributeError, AssertionError):
        raise ValueError("invalid architecture report schema or invariants") from None


class LocalArchitectureReports:
    def validate_destination(
        self,
        destination: Path,
        protected_root: Path | None = None,
        sources: tuple[Path, ...] = (),
    ) -> None:
        LocalGraphArtifacts().validate_destination(destination, protected_root)
        for source in sources:
            LocalGraphArtifacts().validate_destination(destination, source=source)

    def write(self, report: ArchitectureReport, destination: Path) -> ArtifactReference:
        target = destination_path(destination)
        raw = canonical_report(report)
        if len(raw) > MAX_REPORT_BYTES:
            raise ValueError("report exceeds byte limit")
        atomic_write(target, raw)
        return ArtifactReference(
            target.name, ArtifactKind.ARCHITECTURE_REPORT, hashlib.sha256(raw).hexdigest()
        )

    def read(self, source: Path, expected_sha256: str | None = None) -> ArchitectureReport:
        return decode_report(read_artifact(source, expected_sha256, MAX_REPORT_BYTES))
