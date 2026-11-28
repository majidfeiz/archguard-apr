"""Strict import and validation for the frozen V2 provider capability artifact."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path

from archguard.domain.canonical import canonical_json
from archguard.infrastructure.json_codec import unique_object
from archguard.infrastructure.v2_evidence import validate_source_free

MEMBER_NAME = "v2-provider-capability-probe.json"
EXPECTED_ZIP_SHA256 = "598013cd64b2803ae49f5c26afb9734a271abb21e36bce77aa10023fc7b487dc"
EXPECTED_JSON_SHA256 = "8a6f9292b6c9cba66cc990d31172d47eb4aa5e97318c1aaa23cfc1d1fe68d18f"
EXPECTED_RUN_ID = 46128268268
EXPECTED_HEAD_SHA = "e601a8f94a1cb038a13cf0950d3f1cbda70cc61b"
EXPECTED_ARTIFACT_ID = 15257130646
EXPECTED_ARTIFACT_NAME = "v2-provider-capability-probe-observability-fix"
CAPABILITY_FINGERPRINT = "77159d4236788c99bf0886a9108f018035bf4c55307e337fb36c1c3b595d5118"


@dataclass(frozen=True)
class CapabilityArtifactIdentity:
    run_id: int = EXPECTED_RUN_ID
    head_sha: str = EXPECTED_HEAD_SHA
    artifact_id: int = EXPECTED_ARTIFACT_ID
    artifact_name: str = EXPECTED_ARTIFACT_NAME
    zip_sha256: str = EXPECTED_ZIP_SHA256
    json_sha256: str = EXPECTED_JSON_SHA256


EXPECTED_IDENTITY = CapabilityArtifactIdentity()


def validate_capability_artifact(
    archive_path: Path, identity: CapabilityArtifactIdentity = EXPECTED_IDENTITY
) -> bytes:
    raw_archive = archive_path.read_bytes()
    if hashlib.sha256(raw_archive).hexdigest() != identity.zip_sha256:
        raise ValueError("capability artifact ZIP hash mismatch")
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        if len(infos) != 1 or archive.namelist() != [MEMBER_NAME]:
            raise ValueError("capability artifact must contain exactly one allowed member")
        info = infos[0]
        mode = (info.external_attr >> 16) & 0o170000
        if (
            info.is_dir()
            or "/" in info.filename
            or "\\" in info.filename
            or mode not in {0, stat.S_IFREG}
        ):
            raise ValueError("capability artifact member is not a flat regular file")
        if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
            raise ValueError("unsafe capability artifact compression")
        if info.file_size > 64 * 1024 or info.compress_size <= 0:
            raise ValueError("capability artifact member exceeds bounds")
        if info.file_size > max(1024, info.compress_size * 20):
            raise ValueError("unsafe capability artifact compression ratio")
        raw = archive.read(info)
    if hashlib.sha256(raw).hexdigest() != identity.json_sha256:
        raise ValueError("capability evidence JSON hash mismatch")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    except (UnicodeDecodeError, ValueError):
        raise ValueError("capability evidence is not unique-key UTF-8 JSON") from None
    if not isinstance(value, dict) or canonical_json(value) != raw:
        raise ValueError("capability evidence is not canonical JSON")
    validate_source_free(value)
    _validate_evidence(value)
    return raw


def import_capability_evidence(
    archive_path: Path,
    destination: Path,
    identity: CapabilityArtifactIdentity = EXPECTED_IDENTITY,
) -> None:
    raw = validate_capability_artifact(archive_path, identity)
    if destination.exists():
        if destination.is_symlink() or destination.read_bytes() != raw:
            raise ValueError("existing capability evidence contradicts validated artifact")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)


def _validate_evidence(value: dict[str, object]) -> None:
    expected: dict[str, object] = {
        "accepted_provider_calls": 1,
        "api": "responses",
        "diagnostic_fingerprint": CAPABILITY_FINGERPRINT,
        "input_tokens": 137,
        "model": "gpt-5.4-2026-03-05",
        "observed_cost_usd": "0.0014825",
        "output_tokens": 76,
        "patch_semantics_valid": False,
        "provider_request_attempts": 1,
        "response_structure_valid": True,
        "schema": "archguard.v2-provider-capability-probe/v2",
        "scientific_executions": 0,
        "stage": "PATCH_SEMANTIC_VALIDATION",
        "status": "SUPPORTED",
        "strict_schema_accepted": True,
        "tools_disabled": True,
        "usage_returned": True,
    }
    if value != expected:
        raise ValueError("capability evidence contradicts frozen successful observation")
