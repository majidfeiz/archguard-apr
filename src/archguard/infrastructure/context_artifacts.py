"""Strict canonical persistence for source-free and sensitive context artifacts."""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import yaml
from pydantic import TypeAdapter

from archguard.domain.canonical import canonical_json
from archguard.domain.context import (
    CompiledRetrievalQuery,
    ContextBundle,
    RelevanceLabels,
    RetrievalEvaluation,
    RetrievalManifest,
)
from archguard.domain.enums import ArtifactKind
from archguard.domain.models import ArtifactReference
from archguard.infrastructure.artifact_io import atomic_write, destination_path, read_artifact
from archguard.infrastructure.json_codec import unique_object

MAX_CONTEXT_ARTIFACT_BYTES = 32 * 1024 * 1024


def canonical(
    value: CompiledRetrievalQuery | RetrievalManifest | ContextBundle | RetrievalEvaluation,
) -> bytes:
    return canonical_json(asdict(value))


def decode[T](raw: bytes, cls: type[T]) -> T:
    try:
        data = json.loads(
            raw,
            object_pairs_hook=unique_object,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError("non-finite JSON")),
        )
        value = TypeAdapter(cls).validate_json(raw, strict=True)
        if json.loads(canonical(value)) != data:  # type: ignore[arg-type]
            raise ValueError("noncanonical context artifact")
        return value
    except (ValueError, TypeError, KeyError, RecursionError):
        raise ValueError("invalid context artifact schema or fingerprint") from None


class LocalContextArtifacts:
    def _write(
        self,
        value: CompiledRetrievalQuery | RetrievalManifest | ContextBundle | RetrievalEvaluation,
        destination: Path,
        kind: ArtifactKind,
    ) -> ArtifactReference:
        target = destination_path(destination)
        if target.exists():
            raise ValueError("context artifact output already exists")
        raw = canonical(value)
        if len(raw) > MAX_CONTEXT_ARTIFACT_BYTES:
            raise ValueError("context artifact exceeds size limit")
        atomic_write(target, raw)
        return ArtifactReference(target.name, kind, hashlib.sha256(raw).hexdigest())

    def _read[T](self, source: Path, cls: type[T], expected_sha256: str | None = None) -> T:
        return decode(read_artifact(source, expected_sha256, MAX_CONTEXT_ARTIFACT_BYTES), cls)

    def write_query(self, value: CompiledRetrievalQuery, destination: Path) -> ArtifactReference:
        return self._write(value, destination, ArtifactKind.RETRIEVAL_QUERY)

    def read_query(
        self, source: Path, expected_sha256: str | None = None
    ) -> CompiledRetrievalQuery:
        return self._read(source, CompiledRetrievalQuery, expected_sha256)

    def write_manifest(self, value: RetrievalManifest, destination: Path) -> ArtifactReference:
        return self._write(value, destination, ArtifactKind.RETRIEVAL_MANIFEST)

    def read_manifest(self, source: Path, expected_sha256: str | None = None) -> RetrievalManifest:
        return self._read(source, RetrievalManifest, expected_sha256)

    def write_bundle(self, value: ContextBundle, destination: Path) -> ArtifactReference:
        return self._write(value, destination, ArtifactKind.CONTEXT_BUNDLE)

    def read_bundle(self, source: Path, expected_sha256: str | None = None) -> ContextBundle:
        return self._read(source, ContextBundle, expected_sha256)

    def write_evaluation(self, value: RetrievalEvaluation, destination: Path) -> ArtifactReference:
        return self._write(value, destination, ArtifactKind.RETRIEVAL_EVALUATION)

    def read_evaluation(
        self, source: Path, expected_sha256: str | None = None
    ) -> RetrievalEvaluation:
        return self._read(source, RetrievalEvaluation, expected_sha256)


class LocalRelevanceLabels:
    def load(self, source: Path) -> RelevanceLabels:
        raw = read_artifact(source, None, 1024 * 1024)
        try:
            data = yaml.safe_load(raw)
            if not isinstance(data, dict) or set(data) != {
                "retrieval_labels_schema_version",
                "relevant_node_ids",
            }:
                raise ValueError
            if (
                data["retrieval_labels_schema_version"] != "1"
                or not isinstance(data["relevant_node_ids"], list)
                or not all(type(x) is str for x in data["relevant_node_ids"])
            ):
                raise ValueError
            if len(set(data["relevant_node_ids"])) != len(data["relevant_node_ids"]):
                raise ValueError
            return RelevanceLabels.create(tuple(data["relevant_node_ids"]))
        except (yaml.YAMLError, ValueError, TypeError, KeyError):
            raise ValueError("invalid retrieval relevance labels") from None
