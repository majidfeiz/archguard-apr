"""Canonical boundary serialization and content hashing."""

import hashlib
import json
from dataclasses import asdict

from pydantic import TypeAdapter

from archguard.domain.canonical import canonical_json as canonical_json
from archguard.domain.repository import (
    SCHEMA_VERSION,
    AnalysisOptions,
    RepositorySnapshot,
    SourceFileSnapshot,
)
from archguard.infrastructure.json_codec import unique_object


def canonical_snapshot(snapshot: RepositorySnapshot) -> bytes:
    return canonical_json(asdict(snapshot))


def fingerprint(options: AnalysisOptions, files: tuple[SourceFileSnapshot, ...]) -> str:
    """Hash one framed JSON object; skipped/unread files have no content identity."""
    records = [
        [file.path, file.sha256]
        for file in sorted(files, key=lambda f: f.path)
        if file.sha256 is not None
    ]
    return hashlib.sha256(
        canonical_json(
            {
                "schema_version": SCHEMA_VERSION,
                "parser_grammar": "python-3.12",
                "analysis_options": asdict(options),
                "files": records,
            }
        )
    ).hexdigest()


def decode_snapshot(raw: bytes) -> RepositorySnapshot:
    """Strict typed validation plus exact shape round-trip rejects extra/coerced fields."""
    try:
        data = json.loads(raw, object_pairs_hook=unique_object)
        snapshot = TypeAdapter(RepositorySnapshot).validate_json(raw, strict=True)
        if json.loads(canonical_snapshot(snapshot)) != data:
            raise ValueError("noncanonical snapshot structure")
        if (
            fingerprint(snapshot.analysis_options, snapshot.files)
            != snapshot.repository_fingerprint
        ):
            raise ValueError("fingerprint mismatch")
        return snapshot
    except (ValueError, TypeError, KeyError, RecursionError):
        raise ValueError("invalid repository snapshot schema or invariants") from None
