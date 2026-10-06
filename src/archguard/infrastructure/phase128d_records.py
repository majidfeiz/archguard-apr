"""Fail-closed validation for imported Phase 12.8C evidence and profile freeze records."""

import hashlib
import json
from pathlib import Path
from typing import Any

from archguard.domain.canonical import canonical_json
from archguard.domain.orchestration import fingerprint
from archguard.infrastructure.architecture_profiles import LocalArchitectureProfiles
from archguard.infrastructure.json_codec import unique_object
from archguard.infrastructure.phase128b_evidence import BUGGY_REVISION
from archguard.infrastructure.phase128c_evidence import (
    AMENDED_PROFILE_FINGERPRINT,
    OLD_PROFILE_FINGERPRINT,
)

CANONICAL_ARCHIVE_SHA256 = "c737bd847704660eeb13de1a925c65283e98ce3d7fb22ce34cf4dc29b60dbce9"
GITHUB_ARTIFACT_SHA256 = "f99257ebd74d66d5a53242023a30d2f9026590aa42a0e7838c367d69ec07a58b"
MANIFEST_FINGERPRINT = "70305948c61e2dcb662f40ca6c5906f9934c97bcff6c79746ff061186948e5fb"
GRAPH_FINGERPRINT = "261aa8835ff52a407e13d1e9d8f9bbfd06c379b1003121c5633cdcbcf58394ad"
CANONICAL_GRAPH_FINGERPRINT = "b1c318faba70d50225ceba74254edb18727013291de8607695334f8f0a98802c"
CONSTRAINT_FINGERPRINT = "52e1a62506f0c616efa6c3737c073bfa017d94739ac6a1e430e899f761d48075"
DETERMINISM_FINGERPRINT = "a1cae0b8ea43ff162897c4d36e7755fbb0f3fb5341bcef1163d059cf5136a540"
INDEPENDENT_EVIDENCE_SHA256 = "f360d53b815e5960cd516cec5f7dd3d71348d4649f946194bd326d9bbe6958de"
IMPORT_SCHEMA = "archguard.phase-12.8c-evidence-import/v1"
FREEZE_SCHEMA = "archguard.architecture-profile-freeze/v1"


def _load(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(value, dict) or canonical_json(value) != raw:
        raise ValueError("noncanonical Phase 12.8D record")
    body = {key: item for key, item in value.items() if key != "fingerprint"}
    if value.get("fingerprint") != fingerprint(body):
        raise ValueError("Phase 12.8D record fingerprint mismatch")
    return value


def validate_imported_evidence(path: Path) -> dict[str, Any]:
    value = _load(path)
    manifest = value.get("manifest")
    evidence = value.get("evidence")
    if (
        value.get("schema") != IMPORT_SCHEMA
        or not isinstance(manifest, dict)
        or not isinstance(evidence, dict)
    ):
        raise ValueError("invalid imported Phase 12.8C evidence")
    graph = evidence.get("graph_evidence", {})
    evaluation = evidence.get("constraint_evaluation", {})
    deterministic = evidence.get("determinism", {})
    profile = evidence.get("amended_profile_summary", {})
    security = evidence.get("security_scan_summary", {})
    cleanup = evidence.get("cleanup_summary", {})
    readiness = evidence.get("readiness_summary", {})
    if (
        set(evidence)
        != {
            "amended_profile_summary",
            "cleanup_summary",
            "constraint_evaluation",
            "determinism",
            "graph_evidence",
            "manifest",
            "readiness_summary",
            "security_scan_summary",
        }
        or evidence.get("manifest") != manifest
        or value.get("archive_sha256") != CANONICAL_ARCHIVE_SHA256
        or manifest.get("fingerprint") != MANIFEST_FINGERPRINT
        or manifest.get("github_run_id") != "37433179494"
        or manifest.get("task_id") != "PySnooper-2"
        or manifest.get("buggy_revision") != BUGGY_REVISION
        or manifest.get("profile_fingerprint") != AMENDED_PROFILE_FINGERPRINT
        or manifest.get("graph_fingerprint") != GRAPH_FINGERPRINT
        or manifest.get("canonical_graph_fingerprint") != CANONICAL_GRAPH_FINGERPRINT
        or graph.get("fingerprint") != GRAPH_FINGERPRINT
        or evaluation.get("fingerprint") != CONSTRAINT_FINGERPRINT
        or deterministic.get("fingerprint") != DETERMINISM_FINGERPRINT
        or profile.get("old_profile_fingerprint") != OLD_PROFILE_FINGERPRINT
        or graph.get("modules") != 14
        or graph.get("assigned_modules") != 14
        or graph.get("unassigned_modules") != 0
        or graph.get("ambiguous_modules") != 0
        or evaluation.get("enabled_rules") != 5
        or evaluation.get("evaluated_rules") != 5
        or evaluation.get("skipped_rules") != 0
        or evaluation.get("total_violation_count") != 0
        or evaluation.get("partial") is not False
        or evaluation.get("passed") is not True
        or deterministic.get("independent_runs") != 2
        or deterministic.get("byte_identical") is not True
        or deterministic.get("first_evidence_sha256") != INDEPENDENT_EVIDENCE_SHA256
        or deterministic.get("second_evidence_sha256") != INDEPENDENT_EVIDENCE_SHA256
        or security.get("status") != "PASSED"
        or cleanup.get("status") != "COMPLETE"
        or readiness.get("phase_13_ready") is not False
    ):
        raise ValueError("contradictory imported Phase 12.8C evidence")
    return value


def validate_freeze_record(
    freeze_path: Path, profile_path: Path, decision_path: Path, imported_path: Path
) -> dict[str, Any]:
    freeze = _load(freeze_path)
    imported = validate_imported_evidence(imported_path)
    decision_raw = decision_path.read_bytes()
    profile = LocalArchitectureProfiles().load(profile_path)
    if (
        freeze.get("schema") != FREEZE_SCHEMA
        or freeze.get("task_id") != "PySnooper-2"
        or freeze.get("profile_fingerprint") != AMENDED_PROFILE_FINGERPRINT
        or profile.profile_fingerprint != freeze.get("profile_fingerprint")
        or freeze.get("imported_evidence_fingerprint") != imported.get("fingerprint")
        or freeze.get("approval_decision_sha256") != hashlib.sha256(decision_raw).hexdigest()
        or freeze.get("status") != "FROZEN"
        or freeze.get("phase_13_ready") is not False
    ):
        raise ValueError("frozen profile drift or binding mismatch")
    return freeze
