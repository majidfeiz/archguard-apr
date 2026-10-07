"""Strict packaging, validation, and import of Phase 12.8F source-free evidence."""

import hashlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from archguard.domain.canonical import canonical_json
from archguard.domain.orchestration import fingerprint
from archguard.domain.phase128f import (
    QUALIFICATION_SCHEMA,
    SELECTED_TASKS,
    AttemptEvidence,
    Classification,
    Outcome,
    classify,
    qualification_decision,
)
from archguard.infrastructure.json_codec import unique_object

CANDIDATE_FINGERPRINT = "d1068112a12c63e24ee780ad9b31b05c04f9b1417efa50ffa04a1b8b4aac1903"
POLICY_FINGERPRINT = "0987d60ff9b5c2071f0c1dd82a91c680a6aafa885a37b12003bc34dc4add7e01"
ADAPTER_REGISTRY_FINGERPRINT = "614c00ef6d6b8ef370ee99732d5c3534ba066b1347121f8c86d2fd94329974ef"
ADAPTER_IDENTITIES = {
    "PySnooper-1": (
        "55a0d0a4ef2bd8f25d9670330213652b36db785ce50b8bc1d14ab3436f35aed4",
        "e21a31162f4c54be693d8ca8260e42393b39abd3",
        "56f22f8ffe1c6b2be4d2cf3ad1987fdb66113da2",
    ),
    "PySnooper-3": (
        "5154411ea789035bd87e40c7233e52dc9dbfc6b52fc85dd6f7657b89cbc67318",
        "6e3d797be3fa0a746fb5b1b7c7fea78eb926c208",
        "15555ed760000b049aff8fecc79d29339c1224c3",
    ),
    "black-1": (
        "abe97bc7988fe61f8d0c7d64c0f81b4e25cfc1a7f1a83a6a38e0a6461702e5d5",
        "26c9465a22c732ab1e17b0dec578fa3432e9b558",
        "c0a7582e3d4cc8bec3b7f5a6c52b36880dcb57d7",
    ),
    "cookiecutter-4": (
        "4b056f193ff22f8637ccb429d85123aba8cde8f68ab8f3f5506d380cefcd6685",
        "9568ab6ecd2d6836646006c59473c4a4ac0dee04",
        "457a1a4e862aab4102b644ff1d2b2e2b5a766b3c",
    ),
    "black-2": (
        "32b13fa6c4b070849ee30f02f53e8e9ae061cafa88ebf0174e7c9f49ff1f790b",
        "c8ca6b2b9ff3510bee12129824cebfc2fc51e5b2",
        "892eddacd215d685e136686b7f629ade70adca83",
    ),
    "black-3": (
        "d9b829007f76342f37ca6a4caaae46fa0df172ed2813526887bcce65de04c304",
        "8126b4f6a9342290de4655e6a8a78cd288ce7daa",
        "7a14a37981862ef418f3cdb4a7e2375856f97529",
    ),
    "black-4": (
        "713af35b6b7b6e9fd412e4d4ffafba803d4d471274f242cb8ba3f8462bb81e35",
        "65ea568e3301951f26e0e3b98f6d5dc80132e917",
        "c7495b9aa098ef7a358fc74556359d21c6a4ba11",
    ),
}
ARTIFACT_MEMBERS = frozenset(
    {
        "manifest.json",
        "adapter-summary.json",
        "task-qualification.json",
        "fixed-control-summary.json",
        "determinism-summary.json",
        "resource-summary.json",
        "security-scan-summary.json",
        "cleanup-summary.json",
        "readiness-summary.json",
        "SHA256SUMS",
    }
)
MAX_ARTIFACT_BYTES = 10 * 1024**2
FORBIDDEN_KEYS = frozenset(
    {"patch", "gold", "reference_patch", "raw_log", "source", "fixed_code", "expected_lines"}
)


def _load_canonical(raw: bytes) -> dict[str, Any]:
    value = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(value, dict) or canonical_json(value) != raw:
        raise ValueError("noncanonical qualification evidence")
    supplied = value.get("fingerprint")
    body = {key: item for key, item in value.items() if key != "fingerprint"}
    if supplied != fingerprint(body):
        raise ValueError("qualification evidence fingerprint mismatch")
    _reject_sensitive(value)
    return value


def _reject_sensitive(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                raise ValueError("source/gold/raw-log field prohibited")
            _reject_sensitive(item)
    elif isinstance(value, list):
        for item in value:
            _reject_sensitive(item)
    elif isinstance(value, str) and ("diff --git" in value or "@@ -" in value):
        raise ValueError("diff content prohibited")


def _validate_results(value: dict[str, Any]) -> None:
    if value.get("schema") != QUALIFICATION_SCHEMA:
        raise ValueError("unexpected qualification schema")
    results = value.get("results")
    if not isinstance(results, list) or not results:
        raise ValueError("missing task results")
    task_ids = [result.get("task_id") for result in results if isinstance(result, dict)]
    if len(task_ids) != len(results) or len(set(task_ids)) != len(task_ids):
        raise ValueError("duplicate or invalid task results")
    if any(task not in SELECTED_TASKS for task in task_ids):
        raise ValueError("unknown or replacement task")
    for result in results:
        expected_identity = ADAPTER_IDENTITIES.get(result["task_id"])
        supplied_identity = (
            result.get("adapter_fingerprint"),
            result.get("buggy_revision"),
            result.get("fixed_revision"),
        )
        if expected_identity is None or supplied_identity != expected_identity:
            raise ValueError("wrong adapter fingerprint or immutable revision")
        classification = Classification(result.get("classification"))
        fixed_passed = result.get("fixed_control_passed") is True
        prior = result.get("prior_evidence_status")
        expected_decision = qualification_decision(classification, fixed_passed)
        if prior == "EVIDENCE_CONFLICT_REVIEW_REQUIRED":
            expected_decision = "NOT_QUALIFIED"
        if result.get("qualification_decision") != expected_decision:
            raise ValueError("classification/qualification contradiction")
        attempts = result.get("buggy_attempts")
        if classification not in {
            Classification.EVALUATOR_UNAVAILABLE,
            Classification.UNSUPPORTED_ENVIRONMENT,
        }:
            if not isinstance(attempts, list) or len(attempts) != 3:
                raise ValueError("three buggy repetitions required")
            parsed = tuple(
                AttemptEvidence(
                    outcome=Outcome(attempt["outcome"]),
                    exit_code=attempt["exit_code"],
                    failure_signature=attempt["failure_signature"],
                    tests_passed=attempt["tests_passed"],
                    tests_failed=attempt["tests_failed"],
                    duration_milliseconds=attempt["duration_milliseconds"],
                    output_truncated=attempt["output_truncated"],
                )
                for attempt in attempts
            )
            if classify(parsed, fixed_control_passed=fixed_passed) is not classification:
                raise ValueError("classification inconsistent with run evidence")
        if classification is Classification.STABLE:
            signatures = {
                attempt.get("failure_signature")
                for attempt in attempts
                if isinstance(attempt, dict) and attempt.get("outcome") == Outcome.EXPECTED_FAILURE
            }
            if len(signatures) != 1 or None in signatures or not fixed_passed:
                raise ValueError("invalid STABLE evidence")
        if (
            prior == "EVIDENCE_CONFLICT_REVIEW_REQUIRED"
            and result.get("qualification_decision") == "QUALIFIED"
        ):
            raise ValueError("evidence conflict cannot qualify task")


def validate_directory(root: Path) -> dict[str, Any]:
    names = {path.name for path in root.iterdir() if path.is_file()}
    if names != ARTIFACT_MEMBERS or any(not path.is_file() for path in root.iterdir()):
        raise ValueError("unexpected artifact allowlist")
    values = {
        name: _load_canonical((root / name).read_bytes())
        for name in ARTIFACT_MEMBERS
        if name.endswith(".json")
    }
    manifest = values["manifest.json"]
    if (
        manifest.get("candidate_registry_fingerprint") != CANDIDATE_FINGERPRINT
        or manifest.get("selection_policy_fingerprint") != POLICY_FINGERPRINT
        or manifest.get("adapter_registry_fingerprint") != ADAPTER_REGISTRY_FINGERPRINT
        or manifest.get("platform") != "Linux-x86_64"
        or values["security-scan-summary.json"].get("status") != "PASSED"
        or values["cleanup-summary.json"].get("status") != "COMPLETE"
        or values["readiness-summary.json"].get("phase_13_ready") is not False
    ):
        raise ValueError("qualification binding/security/cleanup mismatch")
    _validate_results(values["task-qualification.json"])
    expected = []
    for name in sorted(ARTIFACT_MEMBERS - {"SHA256SUMS"}):
        expected.append(f"{hashlib.sha256((root / name).read_bytes()).hexdigest()}  {name}")
    if (root / "SHA256SUMS").read_text(encoding="utf-8") != "\n".join(expected) + "\n":
        raise ValueError("invalid artifact hashes")
    return manifest


def package(source: Path, archive: Path) -> None:
    validate_directory(source)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for name in sorted(ARTIFACT_MEMBERS):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            output.writestr(info, (source / name).read_bytes())
    if archive.stat().st_size > MAX_ARTIFACT_BYTES:
        archive.unlink()
        raise ValueError("qualification artifact exceeds 10 MiB")


def validate_archive(archive: Path) -> dict[str, Any]:
    if archive.stat().st_size > MAX_ARTIFACT_BYTES:
        raise ValueError("qualification artifact exceeds 10 MiB")
    with zipfile.ZipFile(archive) as source:
        infos = source.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)) or set(names) != ARTIFACT_MEMBERS:
            raise ValueError("duplicate or unexpected artifact member")
        for info in infos:
            path = PurePosixPath(info.filename)
            mode = info.external_attr >> 16
            if path.is_absolute() or ".." in path.parts or not stat.S_ISREG(mode):
                raise ValueError("unsafe ZIP structure")
            if info.file_size > 2 * 1024**2:
                raise ValueError("oversized evidence member")
        temporary = archive.parent / f".{archive.name}.validated"
        temporary.mkdir(exist_ok=False)
        try:
            for info in infos:
                (temporary / info.filename).write_bytes(source.read(info))
            return validate_directory(temporary)
        finally:
            for child in temporary.iterdir():
                child.unlink()
            temporary.rmdir()


def import_archive(archive: Path, output: Path) -> None:
    manifest = validate_archive(archive)
    with zipfile.ZipFile(archive) as source:
        qualification = _load_canonical(source.read("task-qualification.json"))
        fixed_controls = _load_canonical(source.read("fixed-control-summary.json"))
        resources = _load_canonical(source.read("resource-summary.json"))
    payload = {
        "schema": "archguard.phase-12.8f-qualification-import/v1",
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "fixed_controls": fixed_controls,
        "manifest": manifest,
        "phase_13_ready": False,
        "qualification": qualification,
        "resources": resources,
    }
    payload["fingerprint"] = fingerprint(payload)
    encoded = canonical_json(payload)
    if output.exists() and output.read_bytes() != encoded:
        raise ValueError("contradictory prior qualification import")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encoded)
