"""Strict source-free Phase 12.8C profile re-evaluation evidence."""

from __future__ import annotations

import hashlib
import json
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from archguard.domain.canonical import canonical_json
from archguard.domain.orchestration import fingerprint
from archguard.domain.phase128b import ImmutableRevision
from archguard.domain.readiness import sha256_digest
from archguard.infrastructure.architecture_profiles import LocalArchitectureProfiles
from archguard.infrastructure.artifact_io import atomic_write
from archguard.infrastructure.json_codec import unique_object
from archguard.infrastructure.phase128b_evidence import (
    BUGGY_REVISION,
    SOURCE_MARKERS,
    acquire,
    generate_graph_evidence,
)

OLD_PROFILE_FINGERPRINT = "e2694d6a8016382036a3670476d75a0ca16d7f9872678156d16fba6de0f441f1"
AMENDED_PROFILE_FINGERPRINT = "950cd9889d5d4335e60b7429d2feddf2230db42654e5ec844edd813596b6d6d7"
ACQUISITION_FINGERPRINT = "b5820205e5339b0a64a7efdfef6bd74cb71b90d58a18f90fa9847af4123f4c1f"
SCHEMA_PREFIX = "archguard.phase-12.8c"
MAX_ARCHIVE_BYTES = 4 * 1024 * 1024
MAX_MEMBER_BYTES = 1024 * 1024
ARCHIVE_MEMBERS = frozenset(
    {
        "manifest.json",
        "amended-profile-summary.json",
        "graph-evidence.json",
        "constraint-evaluation.json",
        "determinism.json",
        "security-scan-summary.json",
        "cleanup-summary.json",
        "readiness-summary.json",
        "SHA256SUMS",
    }
)
PY_SNOOPER = ImmutableRevision(
    "pysnooper-buggy", "https://github.com/cool-RR/PySnooper.git", BUGGY_REVISION
)


def _record(name: str, body: dict[str, Any]) -> dict[str, Any]:
    value = {"schema": f"{SCHEMA_PREFIX}-{name}/v1", **body}
    value["fingerprint"] = fingerprint(value)
    return value


def _write(path: Path, value: object) -> bytes:
    raw = canonical_json(value)
    atomic_write(path, raw)
    return raw


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_checksums(root: Path) -> None:
    lines = [
        f"{_sha((root / name).read_bytes())}  {name}\n"
        for name in sorted(ARCHIVE_MEMBERS - {"SHA256SUMS"})
    ]
    atomic_write(root / "SHA256SUMS", "".join(lines).encode("ascii"))


def produce(
    external_root: Path, output: Path, repository_root: Path, run_id: str
) -> dict[str, Any]:
    repository = repository_root.resolve(strict=True)
    external = external_root.resolve()
    destination = output.resolve()
    if external.is_relative_to(repository) or destination.is_relative_to(repository):
        raise ValueError("outputs must remain outside analyzed repository")
    if external.is_relative_to(destination) or destination.is_relative_to(external):
        raise ValueError("acquisition and evidence paths must be distinct")
    output.mkdir(parents=True, exist_ok=False)
    checkout = external_root / "pysnooper-buggy"
    disk_bytes = acquire(PY_SNOOPER, checkout, 64 * 1024 * 1024)
    profile_path = repository / "configs/external-profiles/pysnooper-micro-pilot-amended-v2.yaml"
    profile = LocalArchitectureProfiles().load(profile_path)
    if profile.profile_fingerprint != AMENDED_PROFILE_FINGERPRINT:
        raise ValueError("amended profile fingerprint mismatch")
    first, raw_first = generate_graph_evidence(
        checkout, external_root / "run-a", profile_path, AMENDED_PROFILE_FINGERPRINT
    )
    second, raw_second = generate_graph_evidence(
        checkout, external_root / "run-b", profile_path, AMENDED_PROFILE_FINGERPRINT
    )
    if raw_first != raw_second:
        raise ValueError("non-deterministic re-evaluation")
    evaluation = first["constraint_evaluation"]
    if (
        first["modules"] != 14
        or first["assigned_modules"] != 14
        or first["unassigned_modules"] != 0
        or first["ambiguous_modules"] != 0
        or evaluation["skipped_rules"] != 0
    ):
        raise ValueError("AMENDMENT_REQUIRED")
    graph = _record(
        "graph-evidence",
        {
            "task_id": "PySnooper-2",
            "repository_revision": BUGGY_REVISION,
            "profile_fingerprint": AMENDED_PROFILE_FINGERPRINT,
            "canonical_graph_fingerprint": first["canonical_graph_fingerprint"],
            "snapshot_fingerprint": first["snapshot_fingerprint"],
            "modules": first["modules"],
            "assigned_modules": first["assigned_modules"],
            "unassigned_modules": first["unassigned_modules"],
            "ambiguous_modules": first["ambiguous_modules"],
        },
    )
    constraint = _record("constraint-evaluation", evaluation)
    profile_summary = _record(
        "amended-profile-summary",
        {
            "status": "PROPOSED_REEVALUATION_REQUIRED",
            "old_profile_fingerprint": OLD_PROFILE_FINGERPRINT,
            "profile_fingerprint": AMENDED_PROFILE_FINGERPRINT,
            "component": "project-tooling",
            "exact_modules": ["misc.generate_authors", "setup"],
        },
    )
    determinism = _record(
        "determinism",
        {
            "independent_runs": 2,
            "byte_identical": True,
            "canonical_graph_fingerprint": first["canonical_graph_fingerprint"],
            "first_evidence_sha256": _sha(raw_first),
            "second_evidence_sha256": _sha(raw_second),
        },
    )
    readiness = _record(
        "readiness-summary",
        {
            "profile_decision": "AMEND",
            "profile_status": "PROPOSED_REEVALUATION_REQUIRED",
            "architecture_analysis_complete": False,
            "profile_approved": False,
            "profile_frozen": False,
            "phase_13_ready": False,
            "remaining_blocker_codes": [
                "ARCHITECTURE_ANALYSIS_INCOMPLETE",
                "PROFILE_REVIEW_REQUIRED",
            ],
        },
    )
    manifest = _record(
        "manifest",
        {
            "task_id": "PySnooper-2",
            "buggy_revision": BUGGY_REVISION,
            "profile_fingerprint": AMENDED_PROFILE_FINGERPRINT,
            "graph_fingerprint": graph["fingerprint"],
            "canonical_graph_fingerprint": first["canonical_graph_fingerprint"],
            "github_run_id": run_id,
            "phase_13_ready": False,
        },
    )
    for name, value in {
        "manifest.json": manifest,
        "amended-profile-summary.json": profile_summary,
        "graph-evidence.json": graph,
        "constraint-evaluation.json": constraint,
        "determinism.json": determinism,
        "security-scan-summary.json": _record(
            "security-scan-summary", {"status": "PASSED", "forbidden_findings": 0}
        ),
        "cleanup-summary.json": _record(
            "cleanup-summary", {"status": "SCHEDULED", "acquired_disk_bytes": disk_bytes}
        ),
        "readiness-summary.json": readiness,
    }.items():
        _write(output / name, value)
    write_checksums(output)
    return manifest


def finalize_cleanup(root: Path, external_root: Path) -> None:
    if external_root.exists():
        raise ValueError("external root was not removed")
    _write(
        root / "cleanup-summary.json",
        _record("cleanup-summary", {"status": "COMPLETE", "external_root_removed": True}),
    )
    write_checksums(root)
    validate_directory(root)


def _json(raw: bytes) -> dict[str, Any]:
    value = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(value, dict) or canonical_json(value) != raw:
        raise ValueError("noncanonical evidence JSON")
    return value


def validate_directory(root: Path) -> dict[str, Any]:
    entries = list(root.iterdir())
    if {p.name for p in entries} != ARCHIVE_MEMBERS or any(not p.is_file() for p in entries):
        raise ValueError("evidence allowlist mismatch")
    checks: dict[str, str] = {}
    for line in (root / "SHA256SUMS").read_text("ascii").splitlines():
        digest, separator, name = line.partition("  ")
        sha256_digest(digest)
        if separator != "  " or name in checks:
            raise ValueError("invalid checksum manifest")
        checks[name] = digest
    if set(checks) != ARCHIVE_MEMBERS - {"SHA256SUMS"}:
        raise ValueError("incomplete checksum manifest")
    values = {name: _json((root / name).read_bytes()) for name in checks}
    if any(_sha((root / name).read_bytes()) != digest for name, digest in checks.items()):
        raise ValueError("evidence checksum mismatch")
    for name, value in values.items():
        if value.get("schema") != f"{SCHEMA_PREFIX}-{name.removesuffix('.json')}/v1":
            raise ValueError("evidence schema mismatch")
        body = {k: v for k, v in value.items() if k != "fingerprint"}
        if value.get("fingerprint") != fingerprint(body):
            raise ValueError("evidence fingerprint mismatch")
        raw = (root / name).read_bytes().lower()
        if any(marker.lower() in raw for marker in SOURCE_MARKERS) or any(
            marker in raw for marker in (b"gold_patch", b"api_key", b"/users/", b"/home/")
        ):
            raise ValueError("source, gold, secret, log, or environment leakage")
    manifest, graph = values["manifest.json"], values["graph-evidence.json"]
    evaluation, profile = (
        values["constraint-evaluation.json"],
        values["amended-profile-summary.json"],
    )
    deterministic, readiness = values["determinism.json"], values["readiness-summary.json"]
    if (
        manifest.get("task_id") != "PySnooper-2"
        or manifest.get("buggy_revision") != BUGGY_REVISION
        or manifest.get("profile_fingerprint") != AMENDED_PROFILE_FINGERPRINT
        or manifest.get("profile_fingerprint") == OLD_PROFILE_FINGERPRINT
        or graph.get("profile_fingerprint") != manifest.get("profile_fingerprint")
        or graph.get("fingerprint") != manifest.get("graph_fingerprint")
        or graph.get("canonical_graph_fingerprint") != manifest.get("canonical_graph_fingerprint")
        or deterministic.get("canonical_graph_fingerprint")
        != manifest.get("canonical_graph_fingerprint")
        or graph.get("modules") != 14
        or graph.get("assigned_modules") != 14
        or graph.get("unassigned_modules") != 0
        or graph.get("ambiguous_modules") != 0
        or evaluation.get("skipped_rules") != 0
        or profile.get("exact_modules") != ["misc.generate_authors", "setup"]
        or deterministic.get("byte_identical") is not True
        or deterministic.get("independent_runs") != 2
        or values["security-scan-summary.json"].get("status") != "PASSED"
        or values["cleanup-summary.json"].get("status") != "COMPLETE"
        or readiness.get("profile_decision") != "AMEND"
        or readiness.get("profile_status") != "PROPOSED_REEVALUATION_REQUIRED"
        or any(
            readiness.get(k) is not False
            for k in (
                "architecture_analysis_complete",
                "profile_approved",
                "profile_frozen",
                "phase_13_ready",
            )
        )
        or manifest.get("phase_13_ready") is not False
    ):
        raise ValueError("contradictory Phase 12.8C evidence")
    return manifest


def package(root: Path, archive: Path) -> None:
    validate_directory(root)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as target:
        for name in sorted(ARCHIVE_MEMBERS):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            target.writestr(info, (root / name).read_bytes())


def validate_archive(archive: Path) -> dict[str, Any]:
    if archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("archive too large")
    with tempfile.TemporaryDirectory(prefix="archguard-phase128c-") as name:
        root = Path(name)
        with zipfile.ZipFile(archive) as source:
            infos = source.infolist()
            names = [item.filename for item in infos]
            if len(names) != len(set(names)) or set(names) != ARCHIVE_MEMBERS:
                raise ValueError("archive allowlist mismatch")
            for info in infos:
                path, mode = PurePosixPath(info.filename), info.external_attr >> 16
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or len(path.parts) != 1
                    or stat.S_ISLNK(mode)
                    or info.file_size > MAX_MEMBER_BYTES
                ):
                    raise ValueError("unsafe archive member")
                atomic_write(root / info.filename, source.read(info))
        return validate_directory(root)


def import_archive(archive: Path, destination: Path) -> dict[str, Any]:
    manifest = validate_archive(archive)
    value = _record(
        "evidence-import",
        {"archive_sha256": _sha(archive.read_bytes()), "manifest": manifest},
    )
    raw = canonical_json(value)
    if destination.exists() and destination.read_bytes() != raw:
        raise ValueError("contradictory Phase 12.8C import")
    atomic_write(destination, raw)
    return value
