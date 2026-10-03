"""Bounded external acquisition and source-free Phase 12.8B evidence handling."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from archguard.application.services.architecture import EvaluateArchitecture
from archguard.application.services.constraint_engine import DeterministicConstraintEvaluator
from archguard.application.services.graph import BuildRepositoryGraph
from archguard.application.services.graph_builder import DeterministicGraphBuilder
from archguard.application.services.graph_queries import QueryRepositoryGraph
from archguard.application.services.repository import AnalyzeRepository
from archguard.domain.canonical import canonical_json
from archguard.domain.orchestration import fingerprint
from archguard.domain.phase128b import (
    ACQUISITION_SCHEMA,
    ARCHIVE_MEMBERS,
    DETERMINISM_SCHEMA,
    GRAPH_EVIDENCE_SCHEMA,
    LICENSE_REGISTRY_SCHEMA,
    MANIFEST_SCHEMA,
    ImmutableRevision,
    Phase128BManifest,
    fingerprinted,
)
from archguard.domain.readiness import git_sha1_commit, sha256_digest
from archguard.infrastructure.architecture_profiles import LocalArchitectureProfiles
from archguard.infrastructure.architecture_reports import LocalArchitectureReports
from archguard.infrastructure.artifact_io import atomic_write
from archguard.infrastructure.graph_artifacts import LocalGraphArtifacts
from archguard.infrastructure.json_codec import unique_object
from archguard.infrastructure.repository_analyzer import LocalRepositoryAnalyzer
from archguard.infrastructure.repository_artifacts import LocalAnalysisArtifacts

BUGSINPY_REVISION = "11c5f1eea954a42132cfd06bf257766a7963e0fd"
BUGGY_REVISION = "e21a31162f4c54be693d8ca8260e42393b39abd3"
FIXED_REVISION = "814abc34a098c1b98cb327105ac396f985d2413e"
SWEBENCH_REVISION = "02e7a74ffd0b707aab73d203fe87bdc7c76afc8e"
PROFILE_FINGERPRINT = "e2694d6a8016382036a3670476d75a0ca16d7f9872678156d16fba6de0f441f1"
MAX_DOWNLOAD_BYTES = 250 * 1024 * 1024
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_MEMBER_BYTES = 1024 * 1024
SPECS = (
    ImmutableRevision(
        "pysnooper-buggy", "https://github.com/cool-RR/PySnooper.git", BUGGY_REVISION
    ),
    ImmutableRevision(
        "pysnooper-fixed", "https://github.com/cool-RR/PySnooper.git", FIXED_REVISION
    ),
    ImmutableRevision(
        "bugsinpy-metadata", "https://github.com/soarsmu/BugsInPy.git", BUGSINPY_REVISION
    ),
    ImmutableRevision(
        "swe-bench-framework",
        "https://github.com/SWE-bench/SWE-bench.git",
        SWEBENCH_REVISION,
    ),
)
PRIVATE_KEY_MARKER = b"-" * 5 + b"BEGIN " + b"PRIVATE " + b"KEY"
SOURCE_MARKERS = (b"diff --git ", b"@@ -", b"GIT binary patch", PRIVATE_KEY_MARKER)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def tree_bytes(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def _run_git(arguments: list[str], cwd: Path, capture: bool = False) -> str:
    env = {
        **os.environ,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_LFS_SKIP_SMUDGE": "1",
    }
    command = [
        "git",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "submodule.recurse=false",
        *arguments,
    ]
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip() if capture else ""


def validate_acquisition_tree(root: Path, expected_remote: str) -> None:
    resolved = root.resolve(strict=True)
    remote = _run_git(["remote", "get-url", "origin"], resolved, True)
    if remote != expected_remote or _run_git(["remote"], resolved, True) != "origin":
        raise ValueError("unexpected acquisition remote")
    modes = _run_git(["ls-files", "-s"], resolved, True).splitlines()
    if any(line.startswith("160000 ") for line in modes):
        raise ValueError("submodules and gitlinks are forbidden")
    for path in resolved.rglob("*"):
        if path.is_symlink():
            try:
                target = path.resolve(strict=True)
            except OSError:
                raise ValueError("broken acquisition symlink") from None
            if not target.is_relative_to(resolved):
                raise ValueError("symlink escapes acquisition root")
            continue
        if path.is_file() and ".git" not in path.parts:
            with path.open("rb") as stream:
                head = stream.read(256)
            if head.startswith(b"version https://git-lfs.github.com/spec/v1"):
                raise ValueError("Git LFS pointer payload is forbidden")


def acquire(spec: ImmutableRevision, destination: Path, ceiling: int = MAX_DOWNLOAD_BYTES) -> int:
    git_sha1_commit(spec.revision)
    if destination.exists():
        raise ValueError("acquisition destination already exists")
    destination.mkdir(parents=True)
    _run_git(["init", "--quiet"], destination)
    _run_git(["remote", "add", "origin", spec.repository], destination)
    _run_git(
        ["fetch", "--quiet", "--depth=1", "--filter=blob:none", "origin", spec.revision],
        destination,
    )
    _run_git(["checkout", "--quiet", "--detach", "FETCH_HEAD"], destination)
    head = _run_git(["rev-parse", "HEAD"], destination, True)
    if head != spec.revision:
        raise ValueError("acquired revision mismatch")
    validate_acquisition_tree(destination, spec.repository)
    consumed = tree_bytes(destination)
    if consumed > ceiling:
        raise ValueError("acquisition download ceiling exceeded")
    return consumed


def acquire_all(root: Path) -> dict[str, Any]:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    consumed = 0
    for spec in SPECS:
        size = acquire(spec, root / spec.subject, MAX_DOWNLOAD_BYTES - consumed)
        consumed += size
        records.append(
            {
                "subject": spec.subject,
                "repository": spec.repository,
                "revision": spec.revision,
                "head_verified": True,
                "disk_bytes": size,
            }
        )
    return fingerprinted(
        ACQUISITION_SCHEMA,
        {
            "download_ceiling_bytes": MAX_DOWNLOAD_BYTES,
            "measured_disk_bytes": consumed,
            "credentials_required": False,
            "records": records,
        },
    )


def _license_file(root: Path) -> tuple[str, str, str | None] | None:
    matches = [
        path
        for name in ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING")
        if (path := root / name).is_file() and not path.is_symlink()
    ]
    if not matches:
        return None
    path = matches[0]
    raw = path.read_bytes()
    normalized = raw.lower()
    spdx = (
        "MIT"
        if b"permission is hereby granted, free of charge" in normalized
        and b'the software is provided "as is"' in normalized
        else None
    )
    return path.name, sha256(raw), spdx


def audit_licenses(root: Path, timestamp: str) -> dict[str, Any]:
    definitions = (
        ("pysnooper", "project", "pysnooper-buggy", SPECS[0]),
        ("bugsinpy", "framework", "bugsinpy-metadata", SPECS[2]),
        ("swe-bench-framework", "framework", "swe-bench-framework", SPECS[3]),
    )
    records: list[dict[str, Any]] = []
    for subject, kind, directory, spec in definitions:
        found = _license_file(root / directory)
        verified = found is not None and found[2] is not None
        records.append(
            {
                "subject": subject,
                "subject_kind": kind,
                "immutable_revision": spec.revision,
                "official_source_url": spec.repository.removesuffix(".git"),
                "license_identifier": found[2] if found else None,
                "license_file": found[0] if found else None,
                "license_sha256": found[1] if found else None,
                "redistribution": "VERIFIED" if verified else "UNRESOLVED",
                "audit_status": "VERIFIED" if verified else "UNRESOLVED",
                "reason": (
                    "Official immutable license text matched the MIT notice."
                    if verified
                    else "No defensible immutable license identification was available."
                ),
                "evidence_timestamp": timestamp,
            }
        )
    records.append(
        {
            "subject": "swe-bench-verified",
            "subject_kind": "dataset",
            "immutable_revision": "78f471bf655a3137b2e8a75af1501690ec009ec3",
            "official_source_url": "https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified",
            "license_identifier": None,
            "license_file": None,
            "license_sha256": None,
            "redistribution": "UNRESOLVED",
            "audit_status": "UNRESOLVED",
            "reason": "Dataset payload and license were outside the authorized acquisition scope.",
            "evidence_timestamp": timestamp,
        }
    )
    return fingerprinted(
        LICENSE_REGISTRY_SCHEMA,
        {
            "records": records,
            "benchmark_task_redistribution": "UNRESOLVED"
            if any(item["redistribution"] != "VERIFIED" for item in records[:2])
            else "VERIFIED",
            "legal_advice": False,
        },
    )


def generate_graph_evidence(
    source: Path, work: Path, profile_yaml: Path
) -> tuple[dict[str, Any], bytes]:
    work.mkdir(parents=True)
    snapshot_path, graph_path, report_path = (
        work / "snapshot.json",
        work / "graph.json",
        work / "report.json",
    )
    snapshot = (
        AnalyzeRepository(LocalRepositoryAnalyzer(), LocalAnalysisArtifacts())
        .execute(source, output=snapshot_path)
        .snapshot
    )
    graph = (
        BuildRepositoryGraph(
            LocalAnalysisArtifacts(), DeterministicGraphBuilder(), LocalGraphArtifacts()
        )
        .execute(snapshot_path, graph_path, protected_root=source)
        .graph
    )
    profile = LocalArchitectureProfiles().load(profile_yaml)
    if profile.profile_fingerprint != PROFILE_FINGERPRINT:
        raise ValueError("PROFILE_REVIEW_INVALIDATED")
    report = (
        EvaluateArchitecture(
            LocalGraphArtifacts(),
            LocalArchitectureProfiles(),
            DeterministicConstraintEvaluator(),
            LocalArchitectureReports(),
        )
        .execute(graph_path, profile_yaml, report_path, protected_root=source)
        .report
    )
    components = QueryRepositoryGraph(graph).module_components()
    summary = fingerprinted(
        GRAPH_EVIDENCE_SCHEMA,
        {
            "status": "VALIDATED",
            "project": "PySnooper",
            "task_id": "PySnooper-2",
            "repository_revision": BUGGY_REVISION,
            "analyzer_schema_version": snapshot.schema_version,
            "graph_schema_version": graph.graph_schema_version,
            "profile_fingerprint": profile.profile_fingerprint,
            "snapshot_fingerprint": snapshot.repository_fingerprint,
            "canonical_graph_fingerprint": graph.graph_fingerprint,
            "modules": graph.summary.module_nodes,
            "internal_dependency_edges": graph.summary.unique_internal_module_dependencies,
            "external_dependency_edges": graph.summary.external_imports,
            "scc_count": len(components),
            "cycle_count": sum(item.cyclic for item in components),
            "assigned_modules": report.summary.assigned_module_count,
            "unassigned_modules": report.summary.unassigned_module_count,
            "ambiguous_modules": report.summary.ambiguous_module_count,
            "constraint_evaluation": asdict(report.summary),
            "profile_status": "REVIEW_REQUIRED",
            "limitations": [
                "Static analysis cannot observe all dynamic imports or runtime dependencies.",
                "This feasibility evidence is not a final scientific evaluation.",
            ],
        },
    )
    return summary, canonical_json(summary)


def _write_json(path: Path, value: object) -> bytes:
    raw = canonical_json(value)
    atomic_write(path, raw)
    return raw


def scan_source_free(directory: Path) -> dict[str, Any]:
    forbidden_suffixes = {".py", ".patch", ".diff", ".log", ".env", ".pem", ".key"}
    scanned = 0
    for path in directory.iterdir():
        if not path.is_file() or path.name == "SHA256SUMS":
            raise ValueError("unexpected evidence path")
        if path.suffix.lower() in forbidden_suffixes:
            raise ValueError("forbidden evidence member")
        raw = path.read_bytes()
        scanned += len(raw)
        if any(marker in raw for marker in SOURCE_MARKERS) or b"/Users/" in raw or b"/home/" in raw:
            raise ValueError("source, secret, patch, log, or host path leakage")
    return fingerprinted(
        "archguard.phase-12.8b-security-scan/v1",
        {"status": "PASSED", "bytes_scanned": scanned, "forbidden_findings": 0},
    )


def validate_external_paths(external_root: Path, output: Path, repository_root: Path) -> None:
    repository = repository_root.resolve(strict=True)
    if external_root.is_symlink() or output.is_symlink():
        raise ValueError("external evidence paths must not be symlinks")
    external = external_root.resolve()
    destination = output.resolve()
    if external.is_relative_to(repository) or destination.is_relative_to(repository):
        raise ValueError("external evidence paths must be outside the Git repository")
    if destination.is_relative_to(external) or external.is_relative_to(destination):
        raise ValueError("acquisition and source-free evidence paths must be distinct")


def produce_evidence(
    external_root: Path,
    output: Path,
    repository_root: Path,
    github_run_id: str,
    github_job: str,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    validate_external_paths(external_root, output, repository_root)
    acquisitions = external_root / "acquisitions"
    output.mkdir(parents=True, exist_ok=False)
    acquisition = acquire_all(acquisitions)
    timestamp = now().replace(microsecond=0).isoformat().replace("+00:00", "Z")
    licenses = audit_licenses(acquisitions, timestamp)
    profile = repository_root / "configs/external-profiles/pysnooper-micro-pilot.yaml"
    graph_a, raw_a = generate_graph_evidence(
        acquisitions / "pysnooper-buggy", external_root / "run-a", profile
    )
    graph_b, raw_b = generate_graph_evidence(
        acquisitions / "pysnooper-buggy", external_root / "run-b", profile
    )
    if raw_a != raw_b:
        raise ValueError("graph evidence is not byte-identical")
    graph_a["acquisition_manifest_fingerprint"] = acquisition["fingerprint"]
    graph_a["fingerprint"] = fingerprinted(
        GRAPH_EVIDENCE_SCHEMA,
        {k: v for k, v in graph_a.items() if k not in {"schema", "fingerprint"}},
    )["fingerprint"]
    graph_raw = canonical_json(graph_a)
    determinism = fingerprinted(
        DETERMINISM_SCHEMA,
        {
            "independent_runs": 2,
            "byte_identical": True,
            "canonical_graph_fingerprint": graph_a["canonical_graph_fingerprint"],
            "evidence_sha256": sha256(graph_raw),
        },
    )
    architecture_complete = graph_a["unassigned_modules"] == 0 and graph_a["ambiguous_modules"] == 0
    readiness = fingerprinted(
        "archguard.phase-12.8b-readiness-summary/v1",
        {
            "engineering_execution": "SUCCESS",
            "graph_evidence_validated": True,
            "architecture_analysis_complete": architecture_complete,
            "licenses_verified": all(
                item["audit_status"] == "VERIFIED" for item in licenses["records"]
            ),
            "profile_status": "REVIEW_REQUIRED",
            "protocol_status": "REVIEW_REQUIRED",
            "phase_13_ready": False,
            "resolved_blocker_codes": [
                "GRAPH_EVIDENCE_EXTERNAL_EXECUTION_REQUIRED",
                *(["ARCHITECTURE_ANALYSIS_INCOMPLETE"] if architecture_complete else []),
            ],
            "remaining_blocker_codes": [
                "INSUFFICIENT_QUALIFIED_TASKS",
                "INSUFFICIENT_PROJECT_DIVERSITY",
                "INSUFFICIENT_CANDIDATE_POOL",
                "PILOT_SELECTION_NOT_READY",
                "TASK_LIST_NOT_FROZEN",
                "LICENSES_UNVERIFIED",
                "PROFILE_REVIEW_REQUIRED",
                "PROTOCOL_REVIEW_REQUIRED",
                "PROVIDER_NOT_CONFIGURED",
                *([] if architecture_complete else ["ARCHITECTURE_ANALYSIS_INCOMPLETE"]),
            ],
        },
    )
    _write_json(output / "acquisition-summary.json", acquisition)
    _write_json(output / "license-evidence.json", licenses)
    atomic_write(output / "graph-evidence.json", graph_raw)
    _write_json(output / "graph-determinism.json", determinism)
    security = scan_source_free(output)
    _write_json(output / "security-scan-summary.json", security)
    cleanup = fingerprinted(
        "archguard.phase-12.8b-cleanup/v1",
        {"status": "SCHEDULED", "scope": "external_root", "containers_used": False},
    )
    _write_json(output / "cleanup-summary.json", cleanup)
    _write_json(output / "readiness-summary.json", readiness)
    manifest = Phase128BManifest(
        MANIFEST_SCHEMA,
        "PySnooper-2",
        "PySnooper",
        BUGGY_REVISION,
        FIXED_REVISION,
        BUGSINPY_REVISION,
        str(acquisition["fingerprint"]),
        str(licenses["fingerprint"]),
        str(graph_a["fingerprint"]),
        PROFILE_FINGERPRINT,
        github_run_id,
        github_job,
        False,
    )
    _write_json(output / "manifest.json", asdict(manifest))
    write_checksums(output)
    return asdict(manifest)


def write_checksums(directory: Path) -> None:
    names = sorted(ARCHIVE_MEMBERS - {"SHA256SUMS"})
    lines = [f"{sha256((directory / name).read_bytes())}  {name}\n" for name in names]
    atomic_write(directory / "SHA256SUMS", "".join(lines).encode("ascii"))


def finalize_cleanup(directory: Path, external_root: Path) -> dict[str, Any]:
    if external_root.exists():
        raise ValueError("external acquisition root was not cleaned")
    cleanup = fingerprinted(
        "archguard.phase-12.8b-cleanup/v1",
        {
            "status": "COMPLETE",
            "external_root_removed": True,
            "temporary_worktrees_remaining": 0,
            "benchmark_containers_remaining": 0,
            "benchmark_volumes_remaining": 0,
            "benchmark_builders_remaining": 0,
        },
    )
    _write_json(directory / "cleanup-summary.json", cleanup)
    write_checksums(directory)
    validate_evidence_directory(directory)
    return cleanup


def _json(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw, object_pairs_hook=unique_object)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        raise ValueError("invalid evidence JSON") from None
    if not isinstance(value, dict) or canonical_json(value) != raw:
        raise ValueError("noncanonical evidence JSON")
    return value


def validate_evidence_directory(directory: Path) -> dict[str, Any]:
    names = {path.name for path in directory.iterdir() if path.is_file()}
    if names != ARCHIVE_MEMBERS or any(not path.is_file() for path in directory.iterdir()):
        raise ValueError("evidence allowlist mismatch")
    checksums: dict[str, str] = {}
    for line in (directory / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        digest, separator, name = line.partition("  ")
        sha256_digest(digest)
        if separator != "  " or name in checksums or name not in ARCHIVE_MEMBERS - {"SHA256SUMS"}:
            raise ValueError("invalid checksum manifest")
        checksums[name] = digest
    if set(checksums) != ARCHIVE_MEMBERS - {"SHA256SUMS"}:
        raise ValueError("incomplete checksum manifest")
    values = {name: _json((directory / name).read_bytes()) for name in checksums}
    if any(sha256((directory / name).read_bytes()) != digest for name, digest in checksums.items()):
        raise ValueError("evidence checksum mismatch")
    manifest = Phase128BManifest(**values["manifest.json"])
    expected_schemas = {
        "acquisition-summary.json": ACQUISITION_SCHEMA,
        "license-evidence.json": LICENSE_REGISTRY_SCHEMA,
        "graph-evidence.json": GRAPH_EVIDENCE_SCHEMA,
        "graph-determinism.json": DETERMINISM_SCHEMA,
        "security-scan-summary.json": "archguard.phase-12.8b-security-scan/v1",
        "cleanup-summary.json": "archguard.phase-12.8b-cleanup/v1",
        "readiness-summary.json": "archguard.phase-12.8b-readiness-summary/v1",
    }
    for name, schema in expected_schemas.items():
        value = values[name]
        body = {key: item for key, item in value.items() if key != "fingerprint"}
        raw = (directory / name).read_bytes()
        if value.get("schema") != schema or value.get("fingerprint") != fingerprint(body):
            raise ValueError("evidence schema or fingerprint mismatch")
        if any(marker in raw for marker in SOURCE_MARKERS) or b"/Users/" in raw or b"/home/" in raw:
            raise ValueError("evidence leakage detected")
    graph = values["graph-evidence.json"]
    acquisition = values["acquisition-summary.json"]
    licenses = values["license-evidence.json"]
    determinism = values["graph-determinism.json"]
    security = values["security-scan-summary.json"]
    cleanup = values["cleanup-summary.json"]
    readiness = values["readiness-summary.json"]
    acquired = {
        (item.get("subject"), item.get("repository"), item.get("revision"))
        for item in acquisition.get("records", [])
        if isinstance(item, dict)
    }
    expected_acquired = {(item.subject, item.repository, item.revision) for item in SPECS}
    if (
        acquired != expected_acquired
        or acquisition.get("download_ceiling_bytes") != MAX_DOWNLOAD_BYTES
        or int(acquisition.get("measured_disk_bytes", MAX_DOWNLOAD_BYTES + 1)) > MAX_DOWNLOAD_BYTES
        or graph.get("acquisition_manifest_fingerprint") != manifest.acquisition_fingerprint
        or graph.get("repository_revision") != manifest.buggy_revision
        or graph.get("profile_fingerprint") != manifest.profile_fingerprint
        or graph.get("fingerprint") != manifest.graph_fingerprint
        or licenses.get("fingerprint") != manifest.license_fingerprint
        or determinism.get("byte_identical") is not True
        or determinism.get("independent_runs") != 2
        or security.get("status") != "PASSED"
        or cleanup.get("status") != "COMPLETE"
        or readiness.get("phase_13_ready") is not False
        or readiness.get("profile_status") != "REVIEW_REQUIRED"
        or readiness.get("protocol_status") != "REVIEW_REQUIRED"
    ):
        raise ValueError("contradictory evidence conclusions")
    return asdict(manifest)


def create_evidence_zip(directory: Path, archive: Path) -> None:
    validate_evidence_directory(directory)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for name in sorted(ARCHIVE_MEMBERS):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            target.writestr(info, (directory / name).read_bytes())


def validate_evidence_zip(archive: Path) -> dict[str, Any]:
    if archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("evidence archive too large")
    with tempfile.TemporaryDirectory(prefix="archguard-phase128b-", dir=archive.parent) as name:
        temporary = Path(name)
        with zipfile.ZipFile(archive) as source:
            infos = source.infolist()
            names = [item.filename for item in infos]
            if len(names) != len(set(names)) or set(names) != ARCHIVE_MEMBERS:
                raise ValueError("archive member allowlist mismatch")
            for info in infos:
                path = PurePosixPath(info.filename)
                mode = info.external_attr >> 16
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or len(path.parts) != 1
                    or stat.S_ISLNK(mode)
                    or info.file_size > MAX_MEMBER_BYTES
                    or info.compress_size > MAX_MEMBER_BYTES
                ):
                    raise ValueError("unsafe archive member")
                raw = source.read(info)
                if b"\x00" in raw:
                    raise ValueError("binary evidence member")
                atomic_write(temporary / info.filename, raw)
        return validate_evidence_directory(temporary)


def import_evidence_zip(archive: Path, destination: Path) -> dict[str, Any]:
    result = validate_evidence_zip(archive)
    if destination.exists():
        raise ValueError("evidence import destination already exists")
    destination.mkdir(parents=True)
    with zipfile.ZipFile(archive) as source:
        for name in sorted(ARCHIVE_MEMBERS):
            atomic_write(destination / name, source.read(name))
    validate_evidence_directory(destination)
    return result
