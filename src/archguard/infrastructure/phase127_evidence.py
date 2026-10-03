"""Bounded, source-free ingestion of the exact Phase 12.7 Actions artifact."""

import hashlib
import io
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath

from archguard.domain.readiness import IMPORTED_EVIDENCE_SCHEMA, Phase127Evidence
from archguard.infrastructure.artifact_io import atomic_write, destination_path, read_artifact

EXPECTED_SHA256 = "8d3d261e368a1c6bd585f33065cdcda39e4a1924f52ef9763a144d9559f8a498"
MAX_ARCHIVE_BYTES = 10 * 1024 * 1024
MAX_MEMBER_BYTES = 1024 * 1024
MAX_RATIO = 100
EXPECTED_FILES = frozenset(
    {
        "run-metadata.txt",
        "environment.txt",
        "archguard-version.txt",
        "archguard-doctor.txt",
        "readiness-tests.txt",
        "external-preflight-sha256.txt",
        "profile-sha256.txt",
        "profile-status.txt",
        "acquisition-proof.txt",
        "evaluator-image.txt",
        "buggy-run-signatures.txt",
        "buggy-baseline-summary.txt",
        "fixed-control-summary.txt",
        "cleanup-and-quarantine.txt",
        "conclusion.txt",
        "final-resources.txt",
    }
)


def _pairs(raw: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in raw.splitlines():
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in result:
            raise ValueError("duplicate evidence field")
        result[key] = value
    return result


def _read_zip(raw: bytes) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if len(names) != len(set(names)):
            raise ValueError("duplicate ZIP member")
        for info in infos:
            path = PurePosixPath(info.filename)
            mode = info.external_attr >> 16
            if path.is_absolute() or ".." in path.parts or "\\" in info.filename:
                raise ValueError("unsafe ZIP path")
            if info.is_dir() or len(path.parts) != 1:
                raise ValueError("unexpected ZIP layout")
            file_type = stat.S_IFMT(mode)
            if stat.S_ISLNK(mode) or file_type not in {0, stat.S_IFREG}:
                raise ValueError("unexpected ZIP file type")
            if info.file_size > MAX_MEMBER_BYTES:
                raise ValueError("ZIP member too large")
            if info.compress_size == 0 and info.file_size:
                raise ValueError("invalid compression ratio")
            if info.compress_size and info.file_size / info.compress_size > MAX_RATIO:
                raise ValueError("ZIP compression ratio too high")
        if set(names) != EXPECTED_FILES:
            raise ValueError("unexpected evidence file set")
        for name in sorted(EXPECTED_FILES):
            payload = archive.read(name)
            if b"\x00" in payload:
                raise ValueError("binary evidence is forbidden")
            values[name] = payload.decode("utf-8", errors="strict")
    except (zipfile.BadZipFile, UnicodeDecodeError) as error:
        raise ValueError("invalid evidence ZIP") from error
    return values


def validate_phase127_zip(path: Path, expected_sha256: str = EXPECTED_SHA256) -> Phase127Evidence:
    raw = read_artifact(path, expected_sha256, MAX_ARCHIVE_BYTES)
    files = _read_zip(raw)
    metadata = _pairs(files["run-metadata.txt"])
    version = files["archguard-version.txt"].strip()
    profile = _pairs(files["profile-status.txt"])
    acquisition = _pairs(files["acquisition-proof.txt"])
    buggy = _pairs(files["buggy-baseline-summary.txt"])
    fixed = _pairs(files["fixed-control-summary.txt"])
    cleanup = _pairs(files["cleanup-and-quarantine.txt"])
    conclusion = _pairs(files["conclusion.txt"])
    signatures = tuple(
        line.split("signature_sha256=", 1)[1].strip()
        for line in files["buggy-run-signatures.txt"].splitlines()
        if "signature_sha256=" in line
    )
    required_true = (
        acquisition.get("framework_revision_verified"),
        acquisition.get("buggy_revision_verified"),
        acquisition.get("fixed_revision_verified"),
    )
    if metadata.get("schema") != "archguard.phase-12.7-x86-qualification/v1":
        raise ValueError("wrong source evidence schema")
    if required_true != ("true", "true", "true"):
        raise ValueError("revision verification incomplete")
    if buggy.get("classification") != "STABLE" or buggy.get("expected_failure_runs") != "3":
        raise ValueError("contradictory buggy baseline evidence")
    quarantined = (
        all(
            cleanup.get(key) == "0"
            for key in (
                "uploaded_source_files",
                "uploaded_patch_files",
                "uploaded_raw_evaluator_logs",
            )
        )
        and acquisition.get("gold_material_uploaded") == "false"
    )
    return Phase127Evidence(
        schema=IMPORTED_EVIDENCE_SCHEMA,
        archguard_commit=metadata["archguard_commit"],
        archguard_version=version,
        runner_os=metadata["runner_os"],
        host_architecture=metadata["host_architecture"],
        task_id=metadata["task"],
        framework_revision=metadata["bugsinpy_revision"],
        buggy_revision=metadata["buggy_revision"],
        fixed_revision=metadata["fixed_revision"],
        failure_signatures=signatures,
        fixed_control=fixed["trusted_fixed_control"],
        evaluator=fixed["evaluator"],
        profile_compilations=int(profile["profile_compilations"]),
        profile_byte_identical=profile["profile_byte_identical"] == "true",
        cleanup_complete=cleanup.get("remaining_phase_12_7_containers") == "0",
        quarantine_complete=quarantined,
        conclusion="PASSED" if conclusion.get("platform_gate") == "PASSED" else "FAILED",
        provenance={
            "artifact_sha256": hashlib.sha256(raw).hexdigest(),
            "run_url": "https://github.com/majidfeiz/archguard-apr/actions/runs/37009930401",
            "job_url": "https://github.com/majidfeiz/archguard-apr/actions/runs/37009930401/job/110846968717",
        },
    )


def import_phase127_zip(source: Path, destination: Path) -> Phase127Evidence:
    evidence = validate_phase127_zip(source)
    target = destination_path(destination)
    value = as_json(evidence)
    atomic_write(target, value)
    return evidence


def as_json(evidence: Phase127Evidence) -> bytes:
    from dataclasses import asdict

    return (json.dumps(asdict(evidence), sort_keys=True, separators=(",", ":")) + "\n").encode()
