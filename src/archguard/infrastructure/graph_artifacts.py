"""Strict canonical graph serialization and atomic local persistence."""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from pydantic import TypeAdapter

from archguard.application.services.repository import UnsafePathError
from archguard.domain.canonical import canonical_json
from archguard.domain.enums import ArtifactKind
from archguard.domain.graph import RepositoryGraph
from archguard.domain.models import ArtifactReference
from archguard.infrastructure.artifact_io import (
    atomic_write,
    destination_path,
    read_artifact,
)
from archguard.infrastructure.json_codec import unique_object

MAX_GRAPH_BYTES = 64 * 1024 * 1024


def canonical_graph(graph: RepositoryGraph) -> bytes:
    return canonical_json(asdict(graph))


def decode_graph(raw: bytes) -> RepositoryGraph:
    try:
        data = json.loads(raw, object_pairs_hook=unique_object)
        graph = TypeAdapter(RepositoryGraph).validate_json(raw, strict=True)
        if json.loads(canonical_graph(graph)) != data:
            raise ValueError("noncanonical graph structure")
        return graph
    except (ValueError, TypeError, KeyError, RecursionError):
        raise ValueError("invalid repository graph schema or invariants") from None


class LocalGraphArtifacts:
    def validate_destination(
        self, destination: Path, protected_root: Path | None = None, source: Path | None = None
    ) -> None:
        target = destination_path(destination)
        if source is not None and (
            target == source.resolve()
            or (target.exists() and source.exists() and target.samefile(source))
        ):
            raise UnsafePathError("graph output must not replace the input snapshot")
        if protected_root is not None and target.is_relative_to(
            protected_root.resolve(strict=True)
        ):
            raise UnsafePathError("graph output must be outside the protected repository")

    def write(self, graph: RepositoryGraph, destination: Path) -> ArtifactReference:
        target = destination_path(destination)
        raw = canonical_graph(graph)
        atomic_write(target, raw)
        return ArtifactReference(target.name, ArtifactKind.GRAPH, hashlib.sha256(raw).hexdigest())

    def read(self, source: Path, expected_sha256: str | None = None) -> RepositoryGraph:
        return decode_graph(read_artifact(source, expected_sha256, MAX_GRAPH_BYTES))
