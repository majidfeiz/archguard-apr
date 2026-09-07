"""Strict canonical persistence for source-free Phase 5 artifacts."""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from pydantic import TypeAdapter

from archguard.domain.canonical import canonical_json
from archguard.domain.patch_validation import (
    ArchitectureDelta,
    CandidatePatch,
    PatchValidationResult,
)
from archguard.infrastructure.artifact_io import atomic_write, destination_path, read_artifact
from archguard.infrastructure.json_codec import unique_object

MAX_PATCH_ARTIFACT_BYTES = 2 * 1024 * 1024
MAX_DELTA_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_VALIDATION_ARTIFACT_BYTES = 128 * 1024 * 1024


def canonical_patch(value: CandidatePatch) -> bytes:
    return canonical_json(asdict(value))


def canonical_delta(value: ArchitectureDelta) -> bytes:
    return canonical_json(asdict(value))


def canonical_validation(value: PatchValidationResult) -> bytes:
    return canonical_json(asdict(value))


def _decode(
    raw: bytes,
    cls: type[CandidatePatch] | type[ArchitectureDelta] | type[PatchValidationResult],
    canonical: object,
) -> object:
    try:
        data = json.loads(
            raw,
            object_pairs_hook=unique_object,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite JSON")),
        )
        value = TypeAdapter(cls).validate_json(raw, strict=True)
        if json.loads(canonical(value)) != data:  # type: ignore[operator]
            raise ValueError("noncanonical artifact")
        return value
    except (ValueError, TypeError, KeyError, RecursionError, AttributeError):
        raise ValueError("invalid patch-validation artifact") from None


class LocalPatchValidationArtifacts:
    def write_patch(self, patch: CandidatePatch, destination: Path) -> None:
        raw = canonical_patch(patch)
        if len(raw) > MAX_PATCH_ARTIFACT_BYTES:
            raise ValueError("patch metadata artifact exceeds byte limit")
        atomic_write(destination_path(destination), raw)

    def read_patch(self, source: Path, expected_sha256: str | None = None) -> CandidatePatch:
        raw = read_artifact(source, expected_sha256, MAX_PATCH_ARTIFACT_BYTES)
        return _decode(raw, CandidatePatch, canonical_patch)  # type: ignore[return-value]

    def write_delta(self, delta: ArchitectureDelta, destination: Path) -> None:
        raw = canonical_delta(delta)
        if len(raw) > MAX_DELTA_ARTIFACT_BYTES:
            raise ValueError("architecture delta artifact exceeds byte limit")
        atomic_write(destination_path(destination), raw)

    def read_delta(self, source: Path, expected_sha256: str | None = None) -> ArchitectureDelta:
        raw = read_artifact(source, expected_sha256, MAX_DELTA_ARTIFACT_BYTES)
        return _decode(raw, ArchitectureDelta, canonical_delta)  # type: ignore[return-value]

    def write(self, result: PatchValidationResult, destination: Path) -> None:
        raw = canonical_validation(result)
        if len(raw) > MAX_VALIDATION_ARTIFACT_BYTES:
            raise ValueError("validation artifact exceeds byte limit")
        atomic_write(destination_path(destination), raw)

    def read(self, source: Path, expected_sha256: str | None = None) -> PatchValidationResult:
        raw = read_artifact(source, expected_sha256, MAX_VALIDATION_ARTIFACT_BYTES)
        return _decode(raw, PatchValidationResult, canonical_validation)  # type: ignore[return-value]


def artifact_sha256(value: PatchValidationResult) -> str:
    return hashlib.sha256(canonical_validation(value)).hexdigest()
