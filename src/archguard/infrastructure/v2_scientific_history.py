"""Strict validation and immutable import of the first V2 scientific run."""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import zipfile
from pathlib import Path
from typing import cast

from archguard.domain.canonical import canonical_json
from archguard.infrastructure.json_codec import unique_object
from archguard.infrastructure.v2_evidence import validate_source_free

SOURCE_ARTIFACT_SHA256 = "48ce91de65b207ba8791470307e71d08026cec6e8229077cd2a7712d54926b9c"
PREFLIGHT_ARTIFACT_SHA256 = "343206a7ef5c59bdcef6e543418381c2e6aeaf60f6c976427ebd24ccbe688397"
PROTOCOL_FINGERPRINT = "5a110f57dc86e1b4e932bf81e5905a71da65253ab93ed2b68f323f16bd681e05"
PREFIX = "archguard-v2-evidence/"
JSON_MEMBERS = frozenset(
    {
        "aggregate-result.json",
        "attrition-report.json",
        "checkpoint.json",
        "cleanup-report.json",
        "cost-token-ledger.json",
        "execution-01.json",
        "fairness-report.json",
        "run-manifest.json",
    }
)
MEMBER_SHA256 = {
    "aggregate-result.json": "4aa2564cc9724f05b5ac19e30d958297537291da7f40635e81905c1faf06156e",
    "attrition-report.json": "a9314caa32deb06d3ee7c2948b16dc6c540474526ce2fec078e7afe1fb9764cf",
    "checkpoint.json": "e689877a0d2dc6cdc4b0022840e39e20b579f8301b8282acb16825a561aa0dd1",
    "cleanup-report.json": "ce1e234f39c5647515cec7488e9f91d7a8fdd213f46a4eaac5b7a4fe8a3412e6",
    "cost-token-ledger.json": "ea227cab1cd0ed59644eb440a232d919936dbe4f05d3adfd5160b11d4d8bc28d",
    "execution-01.json": "fe50b04417bb85a79666feec397c38a749f31caf92d3cf0ef78dcf37e20dabf2",
    "fairness-report.json": "430ee327a2aeebd48273ac7e0f42a71d20ca2b8b14fb381c16b575c1a9b4928c",
    "run-manifest.json": "be0c58d15bc55c81469c4d13db610f1c3e23a1c302999b3dc532926b5f95c5d9",
}
INNER_MEMBERS = frozenset({"SHA256SUMS", *JSON_MEMBERS})
OUTER_MEMBERS = frozenset(
    {*(PREFIX + name for name in INNER_MEMBERS), "v2-micro-pilot-evidence.zip"}
)
PREFLIGHT_MEMBER = "amended-micro-pilot-readiness.json"


def validate_scientific_archives(source_archive: Path, preflight_archive: Path) -> dict[str, bytes]:
    source_raw = source_archive.read_bytes()
    preflight_raw = preflight_archive.read_bytes()
    _expect_hash(source_raw, SOURCE_ARTIFACT_SHA256, "scientific source artifact")
    _expect_hash(preflight_raw, PREFLIGHT_ARTIFACT_SHA256, "scientific preflight artifact")
    outer = _open_safe(source_raw, OUTER_MEMBERS)
    inner = _open_safe(outer.read("v2-micro-pilot-evidence.zip"), INNER_MEMBERS)
    sums = _checksums(inner.read("SHA256SUMS"))
    if set(sums) != JSON_MEMBERS:
        raise ValueError("scientific evidence checksum membership mismatch")
    imported: dict[str, bytes] = {}
    for name in sorted(JSON_MEMBERS):
        raw = inner.read(name)
        _expect_hash(raw, sums[name], f"scientific evidence member {name}")
        outer_raw = outer.read(PREFIX + name)
        if raw != outer_raw:
            raise ValueError("outer and inner scientific evidence disagree")
        _canonical_source_free(raw)
        imported[name] = raw
    preflight = _open_safe(preflight_raw, frozenset({PREFLIGHT_MEMBER}))
    preflight_value = _canonical_source_free(preflight.read(PREFLIGHT_MEMBER))
    _validate_bindings(imported, preflight_value)
    return imported


def import_scientific_history(
    source_archive: Path, preflight_archive: Path, destination: Path
) -> None:
    imported = validate_scientific_archives(source_archive, preflight_archive)
    destination.mkdir(parents=True, exist_ok=True)
    for name, raw in imported.items():
        path = destination / name
        if path.exists():
            if path.is_symlink() or path.read_bytes() != raw:
                raise ValueError("existing scientific history contradicts validated artifact")
            continue
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)


def validate_frozen_scientific_history(root: Path) -> None:
    directory = root / "research/v2/evidence/scientific-run-1"
    values: dict[str, dict[str, object]] = {}
    for name in JSON_MEMBERS:
        raw = (directory / name).read_bytes()
        _expect_hash(raw, MEMBER_SHA256[name], f"frozen scientific evidence member {name}")
        values[name] = _canonical_source_free(raw)
    _validate_scientific_values(values)
    provenance = _canonical_source_free((directory / "provenance.json").read_bytes())
    if not (
        provenance.get("source_artifact_sha256") == SOURCE_ARTIFACT_SHA256
        and provenance.get("preflight_artifact_sha256") == PREFLIGHT_ARTIFACT_SHA256
        and provenance.get("protocol_fingerprint") == PROTOCOL_FINGERPRINT
    ):
        raise ValueError("scientific history provenance mismatch")


def _open_safe(raw: bytes, expected: frozenset[str]) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise ValueError("invalid scientific evidence ZIP") from None
    infos = archive.infolist()
    names = [info.filename for info in infos]
    if len(names) != len(set(names)) or set(names) != expected:
        raise ValueError("scientific evidence ZIP membership mismatch")
    for info in infos:
        mode = (info.external_attr >> 16) & 0o170000
        if (
            info.is_dir()
            or info.filename.startswith(("/", "\\"))
            or ".." in info.filename.split("/")
            or mode not in {0, stat.S_IFREG}
        ):
            raise ValueError("unsafe scientific evidence member")
        if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
            raise ValueError("unsafe scientific evidence compression")
        if info.file_size > 1024 * 1024 or info.compress_size <= 0:
            raise ValueError("scientific evidence member exceeds bounds")
        if info.file_size > max(1024, info.compress_size * 20):
            raise ValueError("unsafe scientific evidence compression ratio")
    return archive


def _checksums(raw: bytes) -> dict[str, str]:
    try:
        lines = raw.decode("ascii").splitlines()
        pairs = [line.split("  ", 1) for line in lines]
    except UnicodeDecodeError:
        raise ValueError("invalid scientific evidence checksums") from None
    if any(len(pair) != 2 for pair in pairs):
        raise ValueError("invalid scientific evidence checksums")
    values = {name: digest for digest, name in pairs}
    if len(values) != len(pairs) or any(len(value) != 64 for value in values.values()):
        raise ValueError("invalid scientific evidence checksums")
    return values


def _canonical_source_free(raw: bytes) -> dict[str, object]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    except (UnicodeDecodeError, ValueError):
        raise ValueError("scientific evidence is not unique-key UTF-8 JSON") from None
    if not isinstance(value, dict) or canonical_json(value) != raw:
        raise ValueError("scientific evidence is not canonical JSON")
    validate_source_free(value)
    return cast(dict[str, object], value)


def _validate_bindings(imported: dict[str, bytes], preflight: dict[str, object]) -> None:
    values = {name: _canonical_source_free(raw) for name, raw in imported.items()}
    _validate_scientific_values(values)
    if not (
        preflight.get("protocol_fingerprint") == PROTOCOL_FINGERPRINT
        and preflight.get("V2_AMENDED_MICRO_PILOT_READY") is True
        and preflight.get("scientific_checkpoint_state") == "EMPTY_REQUIRED"
    ):
        raise ValueError("scientific preflight protocol binding mismatch")


def _validate_scientific_values(values: dict[str, dict[str, object]]) -> None:
    checkpoint = values["checkpoint.json"]
    ledger = cast(dict[str, object], checkpoint.get("ledger"))
    result = cast(list[dict[str, object]], checkpoint.get("results"))[0]
    failures = cast(list[dict[str, object]], checkpoint.get("provider_failures"))
    run = values["run-manifest.json"]
    if not (
        run.get("protocol_fingerprint") == PROTOCOL_FINGERPRINT
        and ledger.get("provider_request_attempts") == 2
        and ledger.get("accepted_provider_calls") == 1
        and ledger.get("completed_ordinals") == [1]
        and ledger.get("failed_attempt_ordinals") == [2]
        and ledger.get("observed_cost_usd") == "0.0432275"
        and result.get("terminal_classification") == "EXTRACTION_FAILURE"
        and result.get("input_tokens") == 5291
        and result.get("output_tokens") == 2000
        and len(failures) == 1
        and cast(dict[str, object], failures[0].get("diagnostic")).get("fingerprint")
        == "8927b6c24f55a8ff9e42f88d6ab07087e66b1c5b183e7713d250c1a2eddc7bb4"
        and values["cleanup-report.json"].get("complete") is True
        and values["fairness-report.json"].get("status") == "FAIR"
    ):
        raise ValueError("scientific history binding mismatch")


def _expect_hash(raw: bytes, expected: str, label: str) -> None:
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f"{label} hash mismatch")
