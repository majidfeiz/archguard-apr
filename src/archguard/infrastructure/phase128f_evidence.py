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
    EvaluatorRuntimeState,
    FixedControlStage,
    Outcome,
    classify,
    qualification_decision,
)
from archguard.infrastructure.json_codec import unique_object

CANDIDATE_FINGERPRINT = "d1068112a12c63e24ee780ad9b31b05c04f9b1417efa50ffa04a1b8b4aac1903"
POLICY_FINGERPRINT = "0987d60ff9b5c2071f0c1dd82a91c680a6aafa885a37b12003bc34dc4add7e01"
ADAPTER_REGISTRY_FINGERPRINT = "c75006d9b413b991d5227df817c454cb908d4a92705111563ba4f19044923700"
ADAPTER_IDENTITIES = {
    "PySnooper-1": (
        "d3a4938e74e6287056a21ab937a167e18c3c8c0e274a719f713068f28e96db10",
        "e21a31162f4c54be693d8ca8260e42393b39abd3",
        "56f22f8ffe1c6b2be4d2cf3ad1987fdb66113da2",
    ),
    "PySnooper-3": (
        "8be2d7c2752d4a31b101571f85e65416c64243dbaaa46782d5b1efaa3b7fc244",
        "6e3d797be3fa0a746fb5b1b7c7fea78eb926c208",
        "15555ed760000b049aff8fecc79d29339c1224c3",
    ),
    "black-1": (
        "45af5d136425d7378e1a66f5c7deb6cb162442863a353fcb5b795bcef9960162",
        "26c9465a22c732ab1e17b0dec578fa3432e9b558",
        "c0a7582e3d4cc8bec3b7f5a6c52b36880dcb57d7",
    ),
    "cookiecutter-4": (
        "cd1ad0be37d784697a74099fe350a92f6f2f6887eb4553afecb3f200ecf546cf",
        "9568ab6ecd2d6836646006c59473c4a4ac0dee04",
        "457a1a4e862aab4102b644ff1d2b2e2b5a766b3c",
    ),
    "black-2": (
        "f59d4429f66d9b91f8a2b6d0e9eb09f5ca217cd86fdbd7587d76af972662bf48",
        "c8ca6b2b9ff3510bee12129824cebfc2fc51e5b2",
        "892eddacd215d685e136686b7f629ade70adca83",
    ),
    "black-3": (
        "0fce6a06fbe89ec9b88bda5c14fbd430b3a864b68bcc8736a636a5c5caeb515f",
        "8126b4f6a9342290de4655e6a8a78cd288ce7daa",
        "7a14a37981862ef418f3cdb4a7e2375856f97529",
    ),
    "black-4": (
        "fa77421323136ea9b6ee3fef805e9b1e9d2f1eeef5e09a6c4cb512e19dab1fa5",
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


def _validate_runtime_state_machine(value: Any, *, qualified: bool) -> None:
    if not isinstance(value, dict) or value.get("schema") != (
        "archguard.evaluator-runtime-state-machine/v1"
    ):
        raise ValueError("invalid evaluator runtime state-machine schema")
    transitions = value.get("transitions")
    if not isinstance(transitions, list):
        raise ValueError("missing evaluator runtime transitions")
    states = [state.value for state in EvaluatorRuntimeState]
    if len(transitions) > len(states):
        raise ValueError("invalid evaluator runtime transition count")
    reached: list[str] = []
    for index, transition in enumerate(transitions):
        if (
            not isinstance(transition, dict)
            or transition.get("index") != index
            or transition.get("state") != states[index]
            or not isinstance(transition.get("operation_fingerprint"), str)
            or len(transition["operation_fingerprint"]) != 64
        ):
            raise ValueError("invalid evaluator runtime transition")
        reached.append(transition["state"])
    expected_next = states[len(reached)] if len(reached) < len(states) else None
    if (
        value.get("last_reached") != (reached[-1] if reached else None)
        or value.get("next_required") != expected_next
    ):
        raise ValueError("contradictory evaluator runtime transition summary")
    if (
        value.get("transition_fingerprint")
        != hashlib.sha256(canonical_json(transitions)).hexdigest()
    ):
        raise ValueError("evaluator runtime transition fingerprint mismatch")
    if qualified and reached != states:
        raise ValueError("qualified canary did not complete runtime state machine")


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
        if "runtime_state_machine" in result:
            _validate_runtime_state_machine(
                result["runtime_state_machine"],
                qualified=result.get("qualification_decision") == "QUALIFIED",
            )
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
        fixed_control = result.get("fixed_control")
        if not isinstance(fixed_control, dict):
            raise ValueError("missing structured fixed-control evidence")
        required_fixed = {
            "attempted",
            "revision",
            "stage",
            "outcome",
            "exit_code",
            "duration_milliseconds",
            "tests_passed",
            "tests_failed",
            "output_truncated",
            "normalized_failure_class",
            "failure_signature_sha256",
            "evaluator_selector_fingerprint",
            "dependency_environment_fingerprint",
            "image_identity",
            "infrastructure_diagnostic",
        }
        extended_fixed = {
            "collection_count",
            "expected_outcome",
            "expected_test_framework",
            "project_installation_mode",
            "selected_test_fingerprint",
            "source_identity",
        }
        if not required_fixed <= set(fixed_control) or not set(fixed_control) <= (
            required_fixed | extended_fixed
        ):
            raise ValueError("incomplete structured fixed-control evidence")
        FixedControlStage(fixed_control["stage"])
        Outcome(fixed_control["outcome"])
        if fixed_control["outcome"] == Outcome.EXPECTED_FAILURE.value:
            raise ValueError("fixed control cannot use buggy expected-failure semantics")
        if fixed_control.get("expected_outcome", "EXIT_ZERO") != "EXIT_ZERO":
            raise ValueError("invalid fixed-control expectation")
        fixed_record_passed = (
            fixed_control.get("attempted") is True
            and fixed_control.get("outcome") == Outcome.PASS.value
            and fixed_control.get("exit_code") == 0
            and fixed_control.get("infrastructure_diagnostic") is None
        )
        if fixed_passed != fixed_record_passed:
            raise ValueError("contradictory fixed-control result")
        if fixed_control.get("revision") != result.get("fixed_revision") or fixed_control.get(
            "dependency_environment_fingerprint"
        ) != result.get("buggy_environment_fingerprint"):
            raise ValueError("fixed and buggy environment or revision mismatch")
        fixed_source = fixed_control.get("source_identity")
        buggy_source = result.get("buggy_source_identity")
        if fixed_control.get("attempted") is True and "source_identity" in fixed_control:
            collection_count = fixed_control.get("collection_count")
            if (
                not isinstance(collection_count, int)
                or collection_count < 0
                or not fixed_control.get("selected_test_fingerprint")
            ):
                raise ValueError("invalid fixed selector evidence")
            if fixed_record_passed and collection_count < 1:
                raise ValueError("passing fixed selector was not collected")
            if (
                fixed_control.get("normalized_failure_class")
                in {
                    "IMPORT_ERROR",
                    "COLLECTION_ERROR",
                    "SELECTOR_NOT_FOUND",
                }
                and collection_count != 0
            ):
                raise ValueError("collection failure cannot report collected tests")
            if not isinstance(fixed_source, dict) or not isinstance(buggy_source, dict):
                raise ValueError("missing independent source identity")
            for source, revision in (
                (buggy_source, result["buggy_revision"]),
                (fixed_source, result["fixed_revision"]),
            ):
                if any(
                    source.get(key) != revision
                    for key in (
                        "requested_revision",
                        "acquired_repository_revision",
                        "checked_out_head",
                    )
                ):
                    raise ValueError("source revision identity mismatch")
                if source.get("container_visible_source_fingerprint") != source.get(
                    "working_directory_fingerprint"
                ):
                    raise ValueError("container-visible source mismatch")
            if fixed_source.get("git_tree_identity") == buggy_source.get("git_tree_identity"):
                raise ValueError("buggy and fixed source trees must be independent")
            image_identity = fixed_control.get("image_identity") or {}
            if image_identity.get(
                "source_in_image"
            ) != "ABSENT_DEPENDENCY_ONLY" or fixed_source.get(
                "build_context_fingerprint"
            ) != image_identity.get("build_context_fingerprint"):
                raise ValueError("target source leaked into evaluator image")
        base_identity = result.get("base_image_identity")
        if classification is not Classification.INFRASTRUCTURE_FAILURE and (
            not isinstance(base_identity, dict)
            or base_identity.get("architecture") != "amd64"
            or base_identity.get("operating_system") != "linux"
            or not base_identity.get("image_id")
            or result.get("dependency_build_status") != "COMPLETE"
        ):
            raise ValueError("missing base image or dependency-build identity")
        if classification is Classification.INFRASTRUCTURE_FAILURE:
            diagnostic = result.get("infrastructure_diagnostic")
            if (
                result.get("scientific_classification") is not None
                or result.get("execution_status") != "INFRASTRUCTURE_FAILURE"
                or not isinstance(diagnostic, dict)
                or diagnostic.get("failure_stage")
                not in {
                    "SOURCE_ACQUISITION",
                    "IDENTITY_VERIFICATION",
                    "BASE_IMAGE_ACQUISITION",
                    "DEPENDENCY_BUILD",
                    "BUGGY_EXECUTION",
                    "FIXED_CONTROL_EXECUTION",
                    "SECURITY_SCAN",
                    "CLEANUP",
                }
                or result.get("prior_evidence_status") != "NOT_EVALUATED_INFRASTRUCTURE_FAILURE"
            ):
                raise ValueError("incomplete infrastructure diagnostic")
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
                    normalized_failure_class=attempt.get("normalized_failure_class"),
                )
                for attempt in attempts
            )
            reconstructed = classify(parsed, fixed_control_passed=fixed_passed)
            if reconstructed is not classification:
                diagnostic = result.get("infrastructure_diagnostic")
                pre_execution_evaluator_failure = (
                    classification
                    in {
                        Classification.EVALUATOR_ADAPTER_INVALID,
                        Classification.EVALUATOR_ENVIRONMENT_INVALID,
                    }
                    and isinstance(diagnostic, dict)
                    and diagnostic.get("failure_stage")
                    in {"IDENTITY_VERIFICATION", "EVALUATOR_PREFLIGHT"}
                    and result.get("scientific_classification") is None
                    and result.get("execution_status") == "INVALID_EVALUATOR_RESULT"
                    and result.get("prior_evidence_status") == "NOT_EVALUATED_INVALID_EVALUATOR"
                    and fixed_control.get("attempted") is False
                    and all(
                        attempt.outcome is Outcome.INFRASTRUCTURE_FAILURE
                        and attempt.duration_milliseconds == 0
                        for attempt in parsed
                    )
                )
                if (
                    classification
                    not in {
                        Classification.FIXED_CONTROL_FAILED,
                        Classification.FIXED_CONTROL_INFRASTRUCTURE_FAILURE,
                    }
                    and not pre_execution_evaluator_failure
                ):
                    raise ValueError("classification inconsistent with run evidence")
            if classification is Classification.INFRASTRUCTURE_FAILURE and any(
                attempt.duration_milliseconds == 0
                and result["infrastructure_diagnostic"].get("failure_stage") is None
                for attempt in parsed
            ):
                raise ValueError("zero-duration failure requires pre-execution stage")
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
        for artifact in result.get("dependency_artifacts", []):
            if not isinstance(artifact, dict) or not artifact.get("filename"):
                raise ValueError("invalid acquired dependency identity")
            digest = artifact.get("sha256")
            if not isinstance(digest, str) or len(digest) != 64:
                raise ValueError("invalid acquired dependency hash")


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
