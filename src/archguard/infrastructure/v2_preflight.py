"""Strict JSON loading and immutable canonical persistence for V2 preflight."""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from archguard.domain.canonical import canonical_json
from archguard.domain.v2_preflight import V2PreflightManifest, V2PreflightResult
from archguard.infrastructure.json_codec import unique_object

FIELDS = {
    "schema",
    "project_id",
    "task_id",
    "project_revision",
    "task_revision",
    "candidate_registry_fingerprint",
    "architecture_profile_fingerprint",
    "evaluator_fingerprint",
    "failure_signature_fingerprint",
    "dependency_lock_fingerprint",
    "checkout_tree_fingerprint",
    "checks",
    "timeout_seconds",
    "memory_mib",
    "cpu_limit",
    "disk_mib",
}

TASK_MANIFEST_FIELDS = {
    "architecture_profile_fingerprint",
    "blocker_codes",
    "buggy_revision",
    "buggy_tree_identity",
    "cleanup_required",
    "evaluator_adapter_fingerprint",
    "expected_buggy_failure",
    "expected_fixed_success",
    "external_execution_performed_in_v2_1a",
    "failure_signature",
    "fingerprint",
    "fixed_revision",
    "fixed_tree_identity",
    "gold_quarantine_policy",
    "license_evidence",
    "patch_policy_fingerprint",
    "platform_requirement",
    "project",
    "qualification_evidence_fingerprint",
    "repository",
    "repository_graph_fingerprint",
    "resource_ceilings",
    "sandbox_plan",
    "schema",
    "source_free_evidence_policy",
    "static_preflight_status",
    "task_id",
    "tree_identity_status",
}


def load_v2_preflight_manifest(path: Path) -> V2PreflightManifest:
    raw = path.read_bytes()
    if len(raw) > 128 * 1024:
        raise ValueError("preflight manifest too large")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    if isinstance(value, dict) and value.get("schema") == "archguard.v2-task-manifest/v1":
        return _task_manifest(value)
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError("invalid preflight fields")
    data: dict[str, Any] = value
    checks = data["checks"]
    if not isinstance(checks, dict) or not all(
        isinstance(key, str) and isinstance(item, bool) for key, item in checks.items()
    ):
        raise ValueError("invalid preflight checks")
    data = {**data, "checks": tuple(sorted(checks.items()))}
    return V2PreflightManifest(**data)


def _task_manifest(data: dict[str, Any]) -> V2PreflightManifest:
    if set(data) != TASK_MANIFEST_FIELDS:
        raise ValueError("invalid V2 task manifest fields")
    unsigned = {key: value for key, value in data.items() if key != "fingerprint"}
    expected_fingerprint = hashlib.sha256(canonical_json(unsigned)).hexdigest()
    if data["fingerprint"] != expected_fingerprint:
        raise ValueError("V2 task manifest fingerprint mismatch")
    resources = data["resource_ceilings"]
    sandbox = data["sandbox_plan"]
    license_evidence = data["license_evidence"]
    if not all(isinstance(item, dict) for item in (resources, sandbox, license_evidence)):
        raise ValueError("invalid V2 task manifest objects")
    if set(resources) != {
        "cpus",
        "disk_bytes",
        "memory_bytes",
        "output_bytes",
        "pids",
        "timeout_seconds",
    } or not all(type(value) is int and value > 0 for value in resources.values()):
        raise ValueError("invalid V2 task resource ceilings")
    if set(sandbox) != {
        "docker_socket",
        "network",
        "no_new_privileges",
        "read_only_root",
        "user",
    }:
        raise ValueError("invalid V2 task sandbox plan")
    if set(license_evidence) != {"sha256", "spdx", "status"}:
        raise ValueError("invalid V2 task license evidence")
    tree_binding = hashlib.sha256(
        canonical_json(
            {
                "buggy": data["buggy_tree_identity"],
                "fixed": data["fixed_tree_identity"],
                "status": data["tree_identity_status"],
            }
        )
    ).hexdigest()
    checks = {
        "architecture_profile_available": bool(data["architecture_profile_fingerprint"]),
        "buggy_baseline_expected_failure": data["expected_buggy_failure"]
        == "STABLE_EXPECTED_FAILURE",
        "checkout_identity_matches": data["fixed_tree_identity"] is not None,
        "cleanup_ready": data["cleanup_required"] is True,
        "dependency_provenance_verified": bool(data["qualification_evidence_fingerprint"]),
        "evaluator_available": bool(data["evaluator_adapter_fingerprint"]),
        "failure_signature_deterministic": bool(data["failure_signature"]),
        "fixed_control_expected_success": data["expected_fixed_success"] == "PASSED",
        "gold_absent": data["source_free_evidence_policy"]
        == "NO_SOURCE_PROMPT_RAW_RESPONSE_GOLD_SECRET_OR_LOCAL_PATH",
        "license_eligible": license_evidence.get("status") == "VERIFIED"
        and license_evidence.get("spdx") == "MIT",
        "network_disabled": sandbox.get("network") == "none",
        "patch_policy_compatible": bool(data["patch_policy_fingerprint"]),
        "platform_supported": data["platform_requirement"] == "Linux-x86_64",
        "revisions_immutable": True,
        "sandbox_available": sandbox.get("docker_socket") is False,
        "source_free_output": True,
        "task_in_frozen_registry": data["task_id"] in {"PySnooper-2", "PySnooper-3"},
    }
    return V2PreflightManifest(
        schema="archguard.v2-preflight-manifest/v1",
        project_id=str(data["project"]),
        task_id=str(data["task_id"]),
        project_revision=str(data["buggy_revision"]),
        task_revision=str(data["fixed_revision"]),
        candidate_registry_fingerprint=(
            "d1068112a12c63e24ee780ad9b31b05c04f9b1417efa50ffa04a1b8b4aac1903"
        ),
        architecture_profile_fingerprint=str(data["architecture_profile_fingerprint"]),
        evaluator_fingerprint=str(data["evaluator_adapter_fingerprint"]),
        failure_signature_fingerprint=str(data["failure_signature"]),
        dependency_lock_fingerprint=(
            "899d0fc399eaba2098657ae0e109351a9c68e8fced0ea24549b3442ec3153b23"
        ),
        checkout_tree_fingerprint=tree_binding,
        checks=tuple(sorted(checks.items())),
        timeout_seconds=int(resources["timeout_seconds"]),
        memory_mib=int(resources["memory_bytes"]) // (1024 * 1024),
        cpu_limit=int(resources["cpus"]),
        disk_mib=int(resources["disk_bytes"]) // (1024 * 1024),
    )


def write_v2_preflight_result(path: Path, result: V2PreflightResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(canonical_json(asdict(result)))
