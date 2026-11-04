"""Immutable provider-free V2 benchmark readiness contracts."""

import hashlib
from dataclasses import asdict, dataclass
from enum import StrEnum

from archguard.domain.canonical import canonical_json
from archguard.domain.repository import check, digest

PREFLIGHT_MANIFEST_SCHEMA = "archguard.v2-preflight-manifest/v1"
PREFLIGHT_RESULT_SCHEMA = "archguard.v2-preflight-result/v1"


class PreflightBlocker(StrEnum):
    REVISION_NOT_IMMUTABLE = "REVISION_NOT_IMMUTABLE"
    TASK_NOT_IN_FROZEN_REGISTRY = "TASK_NOT_IN_FROZEN_REGISTRY"
    LICENSE_INELIGIBLE = "LICENSE_INELIGIBLE"
    ARCHITECTURE_PROFILE_UNAVAILABLE = "ARCHITECTURE_PROFILE_UNAVAILABLE"
    EVALUATOR_UNAVAILABLE = "EVALUATOR_UNAVAILABLE"
    BUGGY_BASELINE_NOT_REPRODUCED = "BUGGY_BASELINE_NOT_REPRODUCED"
    FIXED_CONTROL_NOT_REPRODUCED = "FIXED_CONTROL_NOT_REPRODUCED"
    FAILURE_SIGNATURE_UNSTABLE = "FAILURE_SIGNATURE_UNSTABLE"
    CHECKOUT_IDENTITY_MISMATCH = "CHECKOUT_IDENTITY_MISMATCH"
    PLATFORM_UNSUPPORTED = "PLATFORM_UNSUPPORTED"
    DEPENDENCY_PROVENANCE_UNVERIFIED = "DEPENDENCY_PROVENANCE_UNVERIFIED"
    SANDBOX_UNAVAILABLE = "SANDBOX_UNAVAILABLE"
    RESOURCE_CEILINGS_INVALID = "RESOURCE_CEILINGS_INVALID"
    NETWORK_ISOLATION_UNAVAILABLE = "NETWORK_ISOLATION_UNAVAILABLE"
    PATCH_POLICY_INCOMPATIBLE = "PATCH_POLICY_INCOMPATIBLE"
    CLEANUP_NOT_READY = "CLEANUP_NOT_READY"
    GOLD_LEAKAGE_DETECTED = "GOLD_LEAKAGE_DETECTED"
    SOURCE_BEARING_OUTPUT_DETECTED = "SOURCE_BEARING_OUTPUT_DETECTED"


@dataclass(frozen=True)
class V2PreflightManifest:
    schema: str
    project_id: str
    task_id: str
    project_revision: str
    task_revision: str
    candidate_registry_fingerprint: str
    architecture_profile_fingerprint: str
    evaluator_fingerprint: str
    failure_signature_fingerprint: str
    dependency_lock_fingerprint: str
    checkout_tree_fingerprint: str
    checks: tuple[tuple[str, bool], ...]
    timeout_seconds: int
    memory_mib: int
    cpu_limit: int
    disk_mib: int

    def __post_init__(self) -> None:
        check(self.schema == PREFLIGHT_MANIFEST_SCHEMA, "unsupported preflight manifest")
        check(bool(self.project_id) and bool(self.task_id), "missing preflight identity")
        for revision in (self.project_revision, self.task_revision):
            check(
                len(revision) == 40 and all(c in "0123456789abcdef" for c in revision),
                "invalid revision",
            )
        for value in (
            self.candidate_registry_fingerprint,
            self.architecture_profile_fingerprint,
            self.evaluator_fingerprint,
            self.failure_signature_fingerprint,
            self.dependency_lock_fingerprint,
            self.checkout_tree_fingerprint,
        ):
            digest(value)
        object.__setattr__(self, "checks", tuple(self.checks))
        check(self.checks == tuple(sorted(self.checks)), "unordered readiness checks")
        check(len(dict(self.checks)) == len(self.checks), "duplicate readiness check")


@dataclass(frozen=True)
class V2PreflightResult:
    schema: str
    project_id: str
    task_id: str
    status: str
    blocker_codes: tuple[PreflightBlocker, ...]
    manifest_fingerprint: str
    result_fingerprint: str
    provider_calls_executed: int = 0
    source_bearing_output: bool = False

    def __post_init__(self) -> None:
        check(self.schema == PREFLIGHT_RESULT_SCHEMA, "unsupported preflight result")
        check(self.status in {"READY", "BLOCKED"}, "invalid readiness status")
        object.__setattr__(self, "blocker_codes", tuple(self.blocker_codes))
        check(self.blocker_codes == tuple(sorted(set(self.blocker_codes))), "unordered blockers")
        check((self.status == "READY") == (not self.blocker_codes), "invalid readiness status")
        check(self.provider_calls_executed == 0, "preflight cannot call a provider")
        check(not self.source_bearing_output, "preflight evidence must be source-free")
        digest(self.manifest_fingerprint)
        expected = _fingerprint(self, "result_fingerprint")
        check(self.result_fingerprint == expected, "preflight result fingerprint mismatch")


CHECK_BLOCKERS = {
    "architecture_profile_available": PreflightBlocker.ARCHITECTURE_PROFILE_UNAVAILABLE,
    "buggy_baseline_expected_failure": PreflightBlocker.BUGGY_BASELINE_NOT_REPRODUCED,
    "checkout_identity_matches": PreflightBlocker.CHECKOUT_IDENTITY_MISMATCH,
    "cleanup_ready": PreflightBlocker.CLEANUP_NOT_READY,
    "dependency_provenance_verified": PreflightBlocker.DEPENDENCY_PROVENANCE_UNVERIFIED,
    "evaluator_available": PreflightBlocker.EVALUATOR_UNAVAILABLE,
    "failure_signature_deterministic": PreflightBlocker.FAILURE_SIGNATURE_UNSTABLE,
    "fixed_control_expected_success": PreflightBlocker.FIXED_CONTROL_NOT_REPRODUCED,
    "gold_absent": PreflightBlocker.GOLD_LEAKAGE_DETECTED,
    "license_eligible": PreflightBlocker.LICENSE_INELIGIBLE,
    "network_disabled": PreflightBlocker.NETWORK_ISOLATION_UNAVAILABLE,
    "patch_policy_compatible": PreflightBlocker.PATCH_POLICY_INCOMPATIBLE,
    "platform_supported": PreflightBlocker.PLATFORM_UNSUPPORTED,
    "revisions_immutable": PreflightBlocker.REVISION_NOT_IMMUTABLE,
    "sandbox_available": PreflightBlocker.SANDBOX_UNAVAILABLE,
    "source_free_output": PreflightBlocker.SOURCE_BEARING_OUTPUT_DETECTED,
    "task_in_frozen_registry": PreflightBlocker.TASK_NOT_IN_FROZEN_REGISTRY,
}


def evaluate_preflight(manifest: V2PreflightManifest) -> V2PreflightResult:
    checks = dict(manifest.checks)
    check(set(checks) == set(CHECK_BLOCKERS), "missing or unknown readiness check")
    blockers = {blocker for name, blocker in CHECK_BLOCKERS.items() if not checks[name]}
    if (
        min(manifest.timeout_seconds, manifest.memory_mib, manifest.cpu_limit, manifest.disk_mib)
        <= 0
    ):
        blockers.add(PreflightBlocker.RESOURCE_CEILINGS_INVALID)
    manifest_fingerprint = hashlib.sha256(canonical_json(asdict(manifest))).hexdigest()
    status = "READY" if not blockers else "BLOCKED"
    blocker_codes = tuple(sorted(blockers))
    values: dict[str, object] = {
        "schema": PREFLIGHT_RESULT_SCHEMA,
        "project_id": manifest.project_id,
        "task_id": manifest.task_id,
        "status": status,
        "blocker_codes": blocker_codes,
        "manifest_fingerprint": manifest_fingerprint,
        "provider_calls_executed": 0,
        "source_bearing_output": False,
    }
    fingerprint = hashlib.sha256(canonical_json(values)).hexdigest()
    return V2PreflightResult(
        schema=PREFLIGHT_RESULT_SCHEMA,
        project_id=manifest.project_id,
        task_id=manifest.task_id,
        status=status,
        blocker_codes=blocker_codes,
        manifest_fingerprint=manifest_fingerprint,
        result_fingerprint=fingerprint,
    )


def _fingerprint(value: V2PreflightResult, excluded: str) -> str:
    data = asdict(value)
    data.pop(excluded)
    return hashlib.sha256(canonical_json(data)).hexdigest()
