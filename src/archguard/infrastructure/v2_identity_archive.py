"""Strict validation and idempotent import of V2.1B identity evidence."""

import hashlib
import json
import stat
import zipfile
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import Any

from archguard.domain.canonical import canonical_json
from archguard.domain.v2_identity import (
    TASK_MANIFEST_FINGERPRINT,
    FixedTreeIdentity,
)
from archguard.infrastructure.json_codec import unique_object

MEMBERS = ("SHA256SUMS", "cleanup-summary.json", "manifest.json", "tree-identity.json")
MAX_MEMBER_BYTES = 65_536
MAX_ARCHIVE_BYTES = 262_144
MAX_COMPRESSION_RATIO = 100


def _fingerprint(data: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in data.items() if key != "fingerprint"}
    return hashlib.sha256(canonical_json(unsigned)).hexdigest()


def _json(data: bytes, name: str) -> dict[str, Any]:
    try:
        text = data.decode("utf-8")
        value = json.loads(text, object_pairs_hook=unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {name}") from error
    if not isinstance(value, dict) or canonical_json(value) != data:
        raise ValueError(f"noncanonical {name}")
    if value.get("fingerprint") != _fingerprint(value):
        raise ValueError(f"invalid {name} fingerprint")
    return value


def _members(archive: Path) -> dict[str, bytes]:
    if archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("identity archive too large")
    with zipfile.ZipFile(archive) as source:
        infos = source.infolist()
        names = [item.filename for item in infos]
        if len(names) != len(set(names)):
            raise ValueError("duplicate archive member")
        if tuple(sorted(names)) != MEMBERS:
            raise ValueError("missing or extra archive member")
        result: dict[str, bytes] = {}
        for info in infos:
            path = PurePosixPath(info.filename)
            mode = info.external_attr >> 16
            if (
                path.is_absolute()
                or len(path.parts) != 1
                or path.parts[0] in {"", ".", ".."}
                or info.is_dir()
                or stat.S_IFMT(mode) not in {0, stat.S_IFREG}
            ):
                raise ValueError("unsafe archive member")
            if info.file_size > MAX_MEMBER_BYTES:
                raise ValueError("oversized archive member")
            if info.file_size and (
                info.compress_size == 0
                or info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
            ):
                raise ValueError("excessive compression ratio")
            result[info.filename] = source.read(info)
    return result


def validate_identity_archive(archive: Path) -> FixedTreeIdentity:
    files = _members(archive)
    evidence_data = _json(files["tree-identity.json"], "tree identity")
    manifest = _json(files["manifest.json"], "manifest")
    cleanup = _json(files["cleanup-summary.json"], "cleanup summary")
    expected_manifest_fields = {
        "schema",
        "task_manifest_fingerprint",
        "tree_identity_sha256",
        "cleanup_summary_sha256",
        "root_tree_object_id",
        "ls_tree_sha256",
        "tree_entry_count",
        "fingerprint",
    }
    if set(manifest) != expected_manifest_fields:
        raise ValueError("invalid manifest fields")
    if manifest["schema"] != "archguard.v2-identity-archive-manifest/v1":
        raise ValueError("invalid manifest schema")
    if manifest["task_manifest_fingerprint"] != TASK_MANIFEST_FINGERPRINT:
        raise ValueError("wrong task manifest fingerprint binding")
    hashes = {
        "tree-identity.json": hashlib.sha256(files["tree-identity.json"]).hexdigest(),
        "cleanup-summary.json": hashlib.sha256(files["cleanup-summary.json"]).hexdigest(),
        "manifest.json": hashlib.sha256(files["manifest.json"]).hexdigest(),
    }
    if manifest["tree_identity_sha256"] != hashes["tree-identity.json"]:
        raise ValueError("invalid tree identity SHA-256")
    if manifest["cleanup_summary_sha256"] != hashes["cleanup-summary.json"]:
        raise ValueError("invalid cleanup summary SHA-256")
    sums = "".join(f"{hashes[name]}  {name}\n" for name in sorted(hashes)).encode()
    if files["SHA256SUMS"] != sums:
        raise ValueError("invalid SHA256SUMS")
    if cleanup != {
        "schema": "archguard.v2-identity-cleanup/v1",
        "cleanup_result": "SUCCEEDED",
        "temporary_repository_removed": True,
        "credential_material_present": False,
        "fingerprint": cleanup["fingerprint"],
    }:
        raise ValueError("invalid cleanup summary")
    expected_evidence_fields = set(FixedTreeIdentity.__dataclass_fields__)
    if set(evidence_data) != expected_evidence_fields:
        raise ValueError("invalid tree identity fields")
    leakage_scan = b"".join(files.values()).lower()
    for marker in (b"../", b"source_canary", b"gold_patch", b"openai_api_key", b"sk-"):
        if marker in leakage_scan:
            raise ValueError("source, gold, or secret leakage marker")
    evidence = FixedTreeIdentity(**evidence_data)
    if evidence.fingerprint != _fingerprint(evidence_data):
        raise ValueError("invalid tree identity fingerprint")
    if (
        manifest["root_tree_object_id"] != evidence.root_tree_object_id
        or manifest["ls_tree_sha256"] != evidence.ls_tree_sha256
        or manifest["tree_entry_count"] != evidence.tree_entry_count
    ):
        raise ValueError("inconsistent tree identity summary")
    return evidence


def import_identity_archive(archive: Path, output: Path) -> FixedTreeIdentity:
    evidence = validate_identity_archive(archive)
    payload = canonical_json(asdict(evidence))
    if output.exists():
        if output.read_bytes() == payload:
            return evidence
        raise ValueError("contradictory existing identity evidence")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(payload)
    return evidence


def write_identity_archive(path: Path, evidence_data: dict[str, Any]) -> None:
    """Write the deterministic flat archive after acquisition cleanup succeeds."""
    evidence_data = {**evidence_data, "fingerprint": _fingerprint(evidence_data)}
    evidence = FixedTreeIdentity(**evidence_data)
    tree = canonical_json(asdict(evidence))
    cleanup = canonical_json(
        {
            "cleanup_result": "SUCCEEDED",
            "credential_material_present": False,
            "fingerprint": hashlib.sha256(
                canonical_json(
                    {
                        "cleanup_result": "SUCCEEDED",
                        "credential_material_present": False,
                        "schema": "archguard.v2-identity-cleanup/v1",
                        "temporary_repository_removed": True,
                    }
                )
            ).hexdigest(),
            "schema": "archguard.v2-identity-cleanup/v1",
            "temporary_repository_removed": True,
        }
    )
    manifest_unsigned = {
        "cleanup_summary_sha256": hashlib.sha256(cleanup).hexdigest(),
        "ls_tree_sha256": evidence.ls_tree_sha256,
        "root_tree_object_id": evidence.root_tree_object_id,
        "schema": "archguard.v2-identity-archive-manifest/v1",
        "task_manifest_fingerprint": TASK_MANIFEST_FINGERPRINT,
        "tree_entry_count": evidence.tree_entry_count,
        "tree_identity_sha256": hashlib.sha256(tree).hexdigest(),
    }
    manifest = canonical_json({**manifest_unsigned, "fingerprint": _fingerprint(manifest_unsigned)})
    files = {
        "cleanup-summary.json": cleanup,
        "manifest.json": manifest,
        "tree-identity.json": tree,
    }
    files["SHA256SUMS"] = "".join(
        f"{hashlib.sha256(files[name]).hexdigest()}  {name}\n" for name in sorted(files)
    ).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        for name in MEMBERS:
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            target.writestr(info, files[name])
    validate_identity_archive(path)
