"""Canonical source-free Phase 7 execution artifact persistence."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import TypeVar

from pydantic import TypeAdapter

from archguard.domain.canonical import canonical_json
from archguard.domain.execution import (
    CandidateValidationReport,
    ExecutionEvidence,
    FunctionalDelta,
)
from archguard.infrastructure.artifact_io import atomic_write, destination_path, read_artifact
from archguard.infrastructure.json_codec import unique_object

Artifact = ExecutionEvidence | FunctionalDelta | CandidateValidationReport
T = TypeVar("T", ExecutionEvidence, FunctionalDelta, CandidateValidationReport)
MAX_EXECUTION_ARTIFACT_BYTES = 32 * 1024 * 1024


def canonical_execution_artifact(value: Artifact) -> bytes:
    return canonical_json(asdict(value))


class LocalExecutionArtifacts:
    def write(self, value: Artifact, destination: Path) -> None:
        raw = canonical_execution_artifact(value)
        if destination.exists():
            raise FileExistsError("immutable execution artifact already exists")
        if len(raw) > MAX_EXECUTION_ARTIFACT_BYTES:
            raise ValueError("execution artifact exceeds byte limit")
        atomic_write(destination_path(destination), raw)

    def read(self, source: Path, cls: type[T], expected_sha256: str | None = None) -> T:
        raw = read_artifact(source, expected_sha256, MAX_EXECUTION_ARTIFACT_BYTES)
        try:
            data = json.loads(raw, object_pairs_hook=unique_object)
            value = TypeAdapter(cls).validate_json(raw, strict=True)
            if json.loads(canonical_execution_artifact(value)) != data:
                raise ValueError("noncanonical artifact")
            return value
        except (ValueError, TypeError, KeyError, RecursionError):
            raise ValueError("invalid execution artifact") from None
