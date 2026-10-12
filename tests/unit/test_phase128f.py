import dataclasses
import hashlib
import json
import stat
import zipfile
from pathlib import Path
from typing import Any

import pytest

from archguard.domain.canonical import canonical_json
from archguard.domain.phase128f import (
    BATCH_A,
    BATCH_B,
    QUALIFICATION_SCHEMA,
    SELECTED_TASKS,
    AttemptEvidence,
    Classification,
    EvaluatorRuntimeState,
    Outcome,
    SandboxContract,
    classify,
    prior_evidence_status,
    qualification_decision,
)
from archguard.infrastructure.phase128f_evidence import (
    ARTIFACT_MEMBERS,
    _validate_results,
    import_archive,
    package,
    validate_archive,
    validate_directory,
)
from scripts.phase128f_evidence import assemble
from scripts.phase128f_registry import adapters, registry
from scripts.phase128f_security_scan import scan

SHA = "a" * 64


def attempt(outcome: Outcome, signature: str | None = SHA) -> AttemptEvidence:
    return AttemptEvidence(
        outcome=outcome,
        exit_code=0 if outcome is Outcome.PASS else 1,
        failure_signature=None if outcome is Outcome.PASS else signature,
        tests_passed=1 if outcome is Outcome.PASS else 0,
        tests_failed=0 if outcome is Outcome.PASS else 1,
        duration_milliseconds=100,
    )


def test_exact_selected_membership_batches_and_no_replacements(repository_root: Path) -> None:
    pool = json.loads((repository_root / "research/candidates/candidate-pool-v1.json").read_text())
    assert tuple(pool["selected_identifiers"]) == SELECTED_TASKS
    assert BATCH_A == ("PySnooper-1", "PySnooper-3", "black-1", "cookiecutter-4")
    assert BATCH_B == ("black-2", "black-3", "black-4")
    assert set(BATCH_A + BATCH_B + ("PySnooper-2",)) == set(SELECTED_TASKS)


def test_adapter_registry_is_deterministic_complete_and_immutable(repository_root: Path) -> None:
    tracked = (repository_root / "research/evaluators/adapter-registry-v2.json").read_bytes()
    assert tracked == canonical_json(registry())
    values = adapters()
    assert len(values) == 7
    assert registry()["fingerprint"] == (
        "61a6b1035efcaeb955c0062d208ff53a762e9584e9ba0294b3dab91c7e984266"
    )
    assert len({item.fingerprint for item in values}) == 7
    assert all(len(item.buggy_revision) == len(item.fixed_revision) == 40 for item in values)
    assert all(item.availability == "AVAILABLE" for item in values)
    assert all(item.evaluator_argv[0] == "python" for item in values)
    assert all(item.constraint_set_fingerprint for item in values)
    assert {item.task_id for item in values if item.review_status == "REVIEWED"} == {
        "PySnooper-1",
        "PySnooper-3",
        "black-1",
        "black-2",
        "black-3",
        "black-4",
        "cookiecutter-4",
    }
    empty = [item for item in values if item.upstream_requirements_empty]
    assert {item.task_id for item in empty} == {"PySnooper-1", "PySnooper-3"}
    assert all(item.dependency_constraints for item in empty)
    assert len({item.constraint_set_fingerprint for item in empty}) == 2
    pool = json.loads((repository_root / "research/candidates/candidate-pool-v1.json").read_text())
    candidates = {item["task_id"]: item for item in pool["observed"]}
    for adapter in values:
        candidate = candidates[adapter.task_id]
        assert (adapter.buggy_revision, adapter.fixed_revision) == (
            candidate["buggy_revision"],
            candidate["fixed_revision"],
        )


def test_final_black_adapters_replace_legacy_identity_fields() -> None:
    reviewed = next(adapter for adapter in adapters() if adapter.task_id == "black-2")
    legacy = dataclasses.replace(
        reviewed,
        schema="archguard.evaluator-adapter/v2",
        buggy_test_selectors=(),
        fixed_test_selectors=(),
        evaluator_source_type="PROJECT_REVISION",
        evaluator_provenance="",
        installation_plan=(),
        expected_framework="",
        quarantine_policy="NONE",
        review_status="LEGACY",
        evaluator_fixture_path=None,
        evaluator_fixture_sha256=None,
        fingerprint="",
    )
    assert legacy.schema == "archguard.evaluator-adapter/v2"
    assert legacy.fingerprint != reviewed.fingerprint


def test_authoritative_phase128e_preflight_binding(repository_root: Path) -> None:
    value = json.loads(
        (repository_root / "research/evidence/phase-12.8e-preflight.json").read_text()
    )
    assert value["github_run_id"] == "37627850370"
    assert value["archive_sha256"] == (
        "195b319a9de6ddacd9d79a0f01a87dd65fed5324e4a92613a754be17dc8f5523"
    )
    assert value["candidate_registry_fingerprint"] == (
        "d1068112a12c63e24ee780ad9b31b05c04f9b1417efa50ffa04a1b8b4aac1903"
    )
    assert value["phase_13_ready"] is False


def test_incomplete_and_replacement_adapter_rejected() -> None:
    base = adapters()[0]
    with pytest.raises(ValueError, match="exact dependency"):
        dataclasses.replace(base, dependency_constraints=())
    with pytest.raises(ValueError, match="unknown adapter"):
        dataclasses.replace(base, task_id="replacement-1", fingerprint="")
    with pytest.raises(ValueError, match="mismatch"):
        dataclasses.replace(base, fingerprint="0" * 64)


def test_sandbox_contract_enforces_network_identity_and_limits() -> None:
    sandbox = SandboxContract()
    assert sandbox.network == "none" and sandbox.user == "non-root"
    assert sandbox.drop_capabilities and sandbox.no_new_privileges
    assert not sandbox.docker_socket and sandbox.source_read_only and sandbox.read_only_root
    with pytest.raises(ValueError):
        dataclasses.replace(sandbox, cpus=3)
    with pytest.raises(ValueError):
        dataclasses.replace(sandbox, memory_bytes=2 * 1024**3 + 1)
    with pytest.raises(ValueError):
        dataclasses.replace(sandbox, pids=257)
    with pytest.raises(ValueError, match="output"):
        dataclasses.replace(sandbox, output_bytes=1024**2 + 1)


def test_three_repetitions_and_stable_signature_classification() -> None:
    stable = (attempt(Outcome.EXPECTED_FAILURE),) * 3
    assert classify(stable, fixed_control_passed=True) is Classification.STABLE
    assert qualification_decision(Classification.STABLE, True) == "QUALIFIED"
    with pytest.raises(ValueError, match="three"):
        classify(stable[:2], fixed_control_passed=True)
    with pytest.raises(ValueError, match="fixed control"):
        qualification_decision(Classification.STABLE, False)


@pytest.mark.parametrize(
    ("attempts", "fixed", "expected"),
    [
        ((attempt(Outcome.PASS),) * 3, True, Classification.NOT_REPRODUCIBLE),
        (
            (
                attempt(Outcome.EXPECTED_FAILURE, "a" * 64),
                attempt(Outcome.EXPECTED_FAILURE, "b" * 64),
                attempt(Outcome.EXPECTED_FAILURE, "a" * 64),
            ),
            True,
            Classification.FLAKY,
        ),
        ((attempt(Outcome.ENVIRONMENT_FAILURE),) * 3, False, Classification.ENVIRONMENT_SENSITIVE),
        ((attempt(Outcome.TIMEOUT),) * 3, False, Classification.SKIPPED_RESOURCE_LIMIT),
        ((attempt(Outcome.RESOURCE_LIMIT),) * 3, False, Classification.SKIPPED_RESOURCE_LIMIT),
        (
            (attempt(Outcome.INFRASTRUCTURE_FAILURE),) * 3,
            False,
            Classification.INFRASTRUCTURE_FAILURE,
        ),
    ],
)
def test_nonstable_scientific_classifications(
    attempts: tuple[AttemptEvidence, ...], fixed: bool, expected: Classification
) -> None:
    assert classify(attempts, fixed_control_passed=fixed) is expected
    assert qualification_decision(expected, fixed) == "NOT_QUALIFIED"


def test_unavailable_unsupported_and_failed_fixed_control() -> None:
    assert (
        classify((), fixed_control_passed=False, adapter_available=False)
        is Classification.EVALUATOR_UNAVAILABLE
    )
    assert (
        classify((), fixed_control_passed=False, environment_supported=False)
        is Classification.UNSUPPORTED_ENVIRONMENT
    )
    stable = (attempt(Outcome.EXPECTED_FAILURE),) * 3
    assert classify(stable, fixed_control_passed=False) is Classification.FIXED_CONTROL_FAILED


@pytest.mark.parametrize(
    ("failure_class", "expected"),
    [
        ("SELECTOR_NOT_FOUND", Classification.EVALUATOR_ADAPTER_INVALID),
        ("COLLECTION_ERROR", Classification.EVALUATOR_ADAPTER_INVALID),
        ("IMPORT_ERROR", Classification.EVALUATOR_ENVIRONMENT_INVALID),
        ("PROJECT_INSTALLATION_ERROR", Classification.EVALUATOR_ENVIRONMENT_INVALID),
        ("PERMISSION_ERROR", Classification.EVALUATOR_ENVIRONMENT_INVALID),
        ("TEST_PROCESS_ERROR", Classification.EVALUATOR_ENVIRONMENT_INVALID),
    ],
)
def test_identical_adapter_failures_are_not_flaky(
    failure_class: str, expected: Classification
) -> None:
    attempt = AttemptEvidence(
        Outcome.OTHER_FAILURE, 1, "a" * 64, 0, 1, 1, normalized_failure_class=failure_class
    )
    assert classify((attempt, attempt, attempt), fixed_control_passed=False) is expected


def test_prior_evidence_is_preserved_and_conflicts_require_review(repository_root: Path) -> None:
    prior = json.loads(
        (repository_root / "research/evidence/qualification-prior-v1.json").read_text()
    )
    from archguard.domain.orchestration import fingerprint

    assert prior["fingerprint"] == fingerprint(
        {key: value for key, value in prior.items() if key != "fingerprint"}
    )
    assert [(item["task_id"], item["classification"]) for item in prior["records"]] == [
        ("PySnooper-1", "NOT_REPRODUCIBLE"),
        ("PySnooper-2", "STABLE"),
        ("PySnooper-3", "STABLE"),
        ("black-1", "EVALUATOR_ENVIRONMENT_INVALID"),
        ("cookiecutter-4", "EVALUATOR_ENVIRONMENT_INVALID"),
    ]
    assert prior_evidence_status("PySnooper-1", Classification.NOT_REPRODUCIBLE) == "CONSISTENT"
    assert prior_evidence_status("PySnooper-1", Classification.STABLE) == (
        "EVIDENCE_CONFLICT_REVIEW_REQUIRED"
    )
    assert prior_evidence_status("black-1", Classification.STABLE) == (
        "EVIDENCE_CONFLICT_REVIEW_REQUIRED"
    )
    assert prior_evidence_status("PySnooper-3", Classification.STABLE) == "CONSISTENT"
    assert (
        prior_evidence_status("black-1", Classification.EVALUATOR_ENVIRONMENT_INVALID)
        == "CONSISTENT"
    )
    assert (
        prior_evidence_status("cookiecutter-4", Classification.EVALUATOR_ENVIRONMENT_INVALID)
        == "CONSISTENT"
    )
    assert prior_evidence_status("black-2", Classification.STABLE) == "NO_PRIOR_EVIDENCE"


def result(task_id: str = "black-1") -> dict[str, Any]:
    adapter = next(item for item in adapters() if item.task_id == task_id)
    attempts = [
        {
            "duration_milliseconds": 100,
            "exit_code": 1,
            "failure_signature": SHA,
            "outcome": "EXPECTED_FAILURE",
            "output_truncated": False,
            "tests_failed": 1,
            "tests_passed": 0,
        }
        for _ in range(3)
    ]
    return {
        "adapter_fingerprint": adapter.fingerprint,
        "base_image_identity": {
            "architecture": "amd64",
            "declared_reference": f"python:{adapter.python_version}",
            "image_id": "sha256:" + SHA,
            "operating_system": "linux",
            "repository_digests": [],
            "repository_tags": [f"python:{adapter.python_version}"],
        },
        "buggy_attempts": attempts,
        "buggy_environment_fingerprint": SHA,
        "buggy_revision": adapter.buggy_revision,
        "buggy_result_status": "BUGGY_RESULT",
        "classification": "STABLE",
        "dependency_artifacts": [{"filename": "dependency.whl", "sha256": SHA}],
        "dependency_build_status": "COMPLETE",
        "execution_status": "SCIENTIFIC_RESULT",
        "fixed_control_passed": True,
        "fixed_control": {
            "attempted": True,
            "dependency_environment_fingerprint": SHA,
            "duration_milliseconds": 100,
            "evaluator_selector_fingerprint": SHA,
            "exit_code": 0,
            "failure_signature_sha256": None,
            "image_identity": {"image_id": "sha256:" + SHA, "tag": "evaluator"},
            "infrastructure_diagnostic": None,
            "normalized_failure_class": None,
            "outcome": "PASS",
            "output_truncated": False,
            "revision": adapter.fixed_revision,
            "stage": "TEST_EXECUTION",
            "tests_failed": 0,
            "tests_passed": 1,
        },
        "fixed_revision": adapter.fixed_revision,
        "infrastructure_diagnostic": None,
        "prior_evidence_status": "NO_PRIOR_EVIDENCE",
        "qualification_decision": "QUALIFIED",
        "scientific_classification": "STABLE",
        "resources": {
            "cpu_limit": 2,
            "memory_limit_bytes": 2 * 1024**3,
            "output_limit_bytes": 1024**2,
            "pids_limit": 256,
            "timeout_seconds": 1200,
        },
        "task_id": task_id,
    }


def _with_source_identities(value: dict[str, Any]) -> dict[str, Any]:
    def identity(revision: str, marker: str) -> dict[str, Any]:
        return {
            "requested_revision": revision,
            "acquired_repository_revision": revision,
            "checked_out_head": revision,
            "git_tree_identity": marker * 40,
            "working_directory_fingerprint": marker * 64,
            "container_visible_source_fingerprint": marker * 64,
            "build_context_fingerprint": "c" * 64,
        }

    fixed = value["fixed_control"]
    fixed.update(
        {
            "collection_count": 1,
            "expected_outcome": "EXIT_ZERO",
            "expected_test_framework": "pytest",
            "project_installation_mode": "DEPENDENCIES_ONLY_NO_TARGET_INSTALL",
            "selected_test_fingerprint": SHA,
            "source_identity": identity(value["fixed_revision"], "b"),
        }
    )
    fixed["image_identity"].update(
        {
            "build_context_fingerprint": "c" * 64,
            "source_in_image": "ABSENT_DEPENDENCY_ONLY",
        }
    )
    value["buggy_source_identity"] = identity(value["buggy_revision"], "a")
    return value


def test_extended_source_identity_contract_and_canaries() -> None:
    valid = _with_source_identities(result())
    _validate_results({"schema": QUALIFICATION_SCHEMA, "results": [valid]})

    fixed_expected = _with_source_identities(result())
    fixed_expected["fixed_control"]["outcome"] = "EXPECTED_FAILURE"
    with pytest.raises(ValueError, match="buggy expected-failure semantics"):
        _validate_results({"schema": QUALIFICATION_SCHEMA, "results": [fixed_expected]})

    wrong_head = _with_source_identities(result())
    wrong_head["fixed_control"]["source_identity"]["checked_out_head"] = "0" * 40
    with pytest.raises(ValueError, match="source revision identity mismatch"):
        _validate_results({"schema": QUALIFICATION_SCHEMA, "results": [wrong_head]})

    stale_mount = _with_source_identities(result())
    stale_mount["fixed_control"]["source_identity"]["container_visible_source_fingerprint"] = (
        "d" * 64
    )
    with pytest.raises(ValueError, match="container-visible source mismatch"):
        _validate_results({"schema": QUALIFICATION_SCHEMA, "results": [stale_mount]})

    shared_tree = _with_source_identities(result())
    shared_tree["fixed_control"]["source_identity"]["git_tree_identity"] = "a" * 40
    with pytest.raises(ValueError, match="must be independent"):
        _validate_results({"schema": QUALIFICATION_SCHEMA, "results": [shared_tree]})

    stale_image = _with_source_identities(result())
    stale_image["fixed_control"]["image_identity"]["build_context_fingerprint"] = "d" * 64
    with pytest.raises(ValueError, match="target source leaked"):
        _validate_results({"schema": QUALIFICATION_SCHEMA, "results": [stale_image]})


def test_qualified_runtime_canary_requires_every_ordered_transition() -> None:
    valid = _with_source_identities(result())
    states = [state.value for state in EvaluatorRuntimeState]
    transitions = [
        {"index": index, "operation_fingerprint": SHA, "state": state}
        for index, state in enumerate(states)
    ]
    valid["runtime_state_machine"] = {
        "schema": "archguard.evaluator-runtime-state-machine/v3",
        "last_reached": states[-1],
        "next_required": None,
        "transition_fingerprint": hashlib.sha256(canonical_json(transitions)).hexdigest(),
        "transitions": transitions,
    }
    _validate_results({"schema": QUALIFICATION_SCHEMA, "results": [valid]})
    valid["runtime_state_machine"]["transitions"][2]["state"] = states[3]
    with pytest.raises(ValueError, match="invalid evaluator runtime transition"):
        _validate_results({"schema": QUALIFICATION_SCHEMA, "results": [valid]})


def test_failed_fixed_selector_can_be_packaged_without_collection() -> None:
    failed = _with_source_identities(result())
    fixed = failed["fixed_control"]
    fixed.update(
        {
            "collection_count": 0,
            "exit_code": 4,
            "failure_signature_sha256": SHA,
            "normalized_failure_class": "SELECTOR_NOT_FOUND",
            "outcome": "OTHER_FAILURE",
            "stage": "TEST_COLLECTION",
            "tests_failed": 1,
            "tests_passed": 0,
        }
    )
    failed.update(
        {
            "classification": "FIXED_CONTROL_FAILED",
            "execution_status": "FIXED_CONTROL_FAILED",
            "fixed_control_passed": False,
            "prior_evidence_status": "NOT_EVALUATED_FIXED_CONTROL_REVIEW_REQUIRED",
            "qualification_decision": "NOT_QUALIFIED",
            "scientific_classification": None,
        }
    )
    _validate_results({"schema": QUALIFICATION_SCHEMA, "results": [failed]})


def test_preflight_evaluator_failure_can_be_packaged_as_non_scientific() -> None:
    failed = result()
    attempts = failed["buggy_attempts"]
    for attempt in attempts:
        attempt.update(
            {
                "duration_milliseconds": 0,
                "exit_code": None,
                "failure_signature": None,
                "normalized_failure_class": "PRE_EXECUTION_INFRASTRUCTURE_FAILURE",
                "outcome": "INFRASTRUCTURE_FAILURE",
                "tests_failed": 0,
                "tests_passed": 0,
            }
        )
    diagnostic = {
        "command_category": "EVALUATOR_PREFLIGHT",
        "failure_code": "PROJECT_IMPORT_FAILED",
        "failure_stage": "EVALUATOR_PREFLIGHT",
        "normalized_error_class": "EvaluatorPreflightError",
        "normalized_stderr_sha256": SHA,
        "process_return_code": None,
        "retryable": False,
    }
    failed["fixed_control"].update(
        {
            "attempted": False,
            "duration_milliseconds": 0,
            "exit_code": None,
            "failure_signature_sha256": SHA,
            "infrastructure_diagnostic": diagnostic,
            "normalized_failure_class": "PROJECT_IMPORT_FAILED",
            "outcome": "INFRASTRUCTURE_FAILURE",
            "stage": "TEST_COLLECTION",
            "tests_failed": 0,
            "tests_passed": 0,
        }
    )
    failed.update(
        {
            "buggy_result_status": "INFRASTRUCTURE_FAILURE",
            "classification": "EVALUATOR_ENVIRONMENT_INVALID",
            "execution_status": "INVALID_EVALUATOR_RESULT",
            "fixed_control_passed": False,
            "infrastructure_diagnostic": diagnostic,
            "prior_evidence_status": "NOT_EVALUATED_INVALID_EVALUATOR",
            "qualification_decision": "NOT_QUALIFIED",
            "scientific_classification": None,
        }
    )
    _validate_results({"schema": QUALIFICATION_SCHEMA, "results": [failed]})
    failed["infrastructure_diagnostic"]["failure_stage"] = "BUGGY_EXECUTION"
    with pytest.raises(ValueError, match="classification inconsistent"):
        _validate_results({"schema": QUALIFICATION_SCHEMA, "results": [failed]})


def test_passing_fixed_selector_requires_collection() -> None:
    invalid = _with_source_identities(result())
    invalid["fixed_control"]["collection_count"] = 0
    with pytest.raises(ValueError, match="passing fixed selector was not collected"):
        _validate_results({"schema": QUALIFICATION_SCHEMA, "results": [invalid]})


@pytest.fixture
def evidence(repository_root: Path, tmp_path: Path) -> tuple[Path, Path]:
    results = tmp_path / "results.json"
    results.write_text(json.dumps([result()]), encoding="utf-8")
    security = tmp_path / "security.json"
    security.write_bytes(
        canonical_json(
            scan(
                (
                    results,
                    repository_root / "research/evaluators/adapter-registry-v2.json",
                )
            )
        )
    )
    root = tmp_path / "evidence"
    assemble(
        results,
        repository_root / "research/evaluators/adapter-registry-v2.json",
        root,
        "12345",
        security,
    )
    archive = tmp_path / "evidence.zip"
    package(root, archive)
    return root, archive


def test_artifact_allowlist_packaging_and_deterministic_import(
    evidence: tuple[Path, Path], tmp_path: Path
) -> None:
    root, archive = evidence
    assert {path.name for path in root.iterdir()} == ARTIFACT_MEMBERS
    assert validate_directory(root)["platform"] == "Linux-x86_64"
    second = tmp_path / "second.zip"
    package(root, second)
    assert archive.read_bytes() == second.read_bytes()
    output = tmp_path / "import.json"
    import_archive(archive, output)
    before = output.read_bytes()
    import_archive(archive, output)
    assert output.read_bytes() == before
    imported = json.loads(before)
    assert imported["phase_13_ready"] is False
    assert imported["qualification"]["results"][0]["task_id"] == "black-1"


def test_successful_scanner_receipt_is_required_before_assembly(
    repository_root: Path, tmp_path: Path
) -> None:
    results = tmp_path / "results.json"
    results.write_text(json.dumps([result()]), encoding="utf-8")
    receipt = tmp_path / "security.json"
    receipt.write_text(json.dumps({"status": "FAILED"}), encoding="utf-8")
    with pytest.raises(ValueError, match="successful security scan"):
        assemble(
            results,
            repository_root / "research/evaluators/adapter-registry-v2.json",
            tmp_path / "evidence",
            "12345",
            receipt,
        )


def test_fixed_and_buggy_environment_mismatch_is_rejected() -> None:
    contradictory = result()
    contradictory["fixed_control"]["dependency_environment_fingerprint"] = "b" * 64
    with pytest.raises(ValueError, match="environment"):
        _validate_results({"schema": QUALIFICATION_SCHEMA, "results": [contradictory]})


def test_fixed_control_record_is_mandatory_and_exact() -> None:
    missing = result()
    missing.pop("fixed_control")
    with pytest.raises(ValueError, match="missing structured"):
        _validate_results({"schema": QUALIFICATION_SCHEMA, "results": [missing]})
    incomplete = result()
    incomplete["fixed_control"].pop("stage")
    with pytest.raises(ValueError, match="incomplete structured"):
        _validate_results({"schema": QUALIFICATION_SCHEMA, "results": [incomplete]})


@pytest.mark.parametrize("name", ["../escape", "/absolute", "unexpected.json"])
def test_archive_rejects_traversal_and_unexpected_members(
    evidence: tuple[Path, Path], tmp_path: Path, name: str
) -> None:
    _, archive = evidence
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(bad, "w") as output:
        for info in source.infolist():
            output.writestr(info, source.read(info))
        output.writestr(name, b"{}\n")
    with pytest.raises(ValueError, match="unexpected|unsafe"):
        validate_archive(bad)


def test_archive_rejects_duplicate_and_symlink(evidence: tuple[Path, Path], tmp_path: Path) -> None:
    _, archive = evidence
    duplicate = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(duplicate, "w") as output:
        for info in source.infolist():
            output.writestr(info, source.read(info))
        output.writestr("manifest.json", b"{}\n")
    with pytest.raises(ValueError, match="duplicate"):
        validate_archive(duplicate)
    symlink = tmp_path / "symlink.zip"
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(symlink, "w") as output:
        for info in source.infolist():
            if info.filename == "manifest.json":
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
            output.writestr(info, source.read(info))
    with pytest.raises(ValueError, match="unsafe"):
        validate_archive(symlink)


def test_stable_without_fixed_control_and_leakage_are_rejected(
    evidence: tuple[Path, Path], tmp_path: Path
) -> None:
    root, _ = evidence
    value = json.loads((root / "task-qualification.json").read_text())
    value["results"][0]["fixed_control_passed"] = False
    body = {key: item for key, item in value.items() if key != "fingerprint"}
    from archguard.domain.orchestration import fingerprint

    value["fingerprint"] = fingerprint(body)
    (root / "task-qualification.json").write_bytes(canonical_json(value))
    with pytest.raises(ValueError, match="fixed.control"):
        validate_directory(root)
    value["results"][0]["raw_log"] = "forbidden"
    with pytest.raises(ValueError, match="prohibited"):
        from archguard.infrastructure.phase128f_evidence import _reject_sensitive

        _reject_sensitive(value)


def test_import_rejects_changed_adapter_identity_and_accepts_conflict_hold() -> None:
    changed = result()
    changed["buggy_revision"] = "0" * 40
    with pytest.raises(ValueError, match="adapter fingerprint or immutable revision"):
        _validate_results({"schema": QUALIFICATION_SCHEMA, "results": [changed]})

    conflict = result("PySnooper-1")
    conflict["prior_evidence_status"] = "EVIDENCE_CONFLICT_REVIEW_REQUIRED"
    conflict["qualification_decision"] = "NOT_QUALIFIED"
    _validate_results({"schema": QUALIFICATION_SCHEMA, "results": [conflict]})


def test_source_free_infrastructure_diagnostic_is_validated() -> None:
    failed = result("PySnooper-1")
    failed.update(
        {
            "base_image_identity": None,
            "buggy_environment_fingerprint": None,
            "buggy_result_status": "INFRASTRUCTURE_FAILURE",
            "buggy_attempts": [
                {
                    "duration_milliseconds": 0,
                    "exit_code": None,
                    "failure_signature": None,
                    "outcome": "INFRASTRUCTURE_FAILURE",
                    "output_truncated": False,
                    "tests_failed": 0,
                    "tests_passed": 0,
                }
                for _ in range(3)
            ],
            "classification": "INFRASTRUCTURE_FAILURE",
            "dependency_artifacts": [],
            "dependency_build_status": "NOT_STARTED",
            "execution_status": "INFRASTRUCTURE_FAILURE",
            "fixed_control_passed": False,
            "fixed_control": {
                "attempted": False,
                "dependency_environment_fingerprint": None,
                "duration_milliseconds": 0,
                "evaluator_selector_fingerprint": SHA,
                "exit_code": None,
                "failure_signature_sha256": SHA,
                "image_identity": None,
                "infrastructure_diagnostic": {"failure_stage": "BASE_IMAGE_ACQUISITION"},
                "normalized_failure_class": "BASE_IMAGE_ACQUISITION_FAILED",
                "outcome": "INFRASTRUCTURE_FAILURE",
                "output_truncated": False,
                "revision": failed["fixed_revision"],
                "stage": "IMAGE_BUILD",
                "tests_failed": 0,
                "tests_passed": 0,
            },
            "infrastructure_diagnostic": {
                "command_category": "BASE_IMAGE_ACQUISITION",
                "failure_code": "BASE_IMAGE_ACQUISITION_FAILED",
                "failure_stage": "BASE_IMAGE_ACQUISITION",
                "normalized_error_class": "CalledProcessError",
                "normalized_stderr_sha256": SHA,
                "process_return_code": 1,
                "retryable": True,
            },
            "prior_evidence_status": "NOT_EVALUATED_INFRASTRUCTURE_FAILURE",
            "qualification_decision": "NOT_QUALIFIED",
            "scientific_classification": None,
        }
    )
    _validate_results({"schema": QUALIFICATION_SCHEMA, "results": [failed]})
    failed["prior_evidence_status"] = "EVIDENCE_CONFLICT_REVIEW_REQUIRED"
    with pytest.raises(ValueError, match="incomplete infrastructure diagnostic"):
        _validate_results({"schema": QUALIFICATION_SCHEMA, "results": [failed]})


def test_frozen_state_and_phase13_remain_unchanged(repository_root: Path) -> None:
    expected = {
        "research/profiles/pysnooper-profile-freeze.json": (
            "345b134bfb1f3e3faf6a8fe08b9edb870b92c25242e9f86edbcb3344a78d91f3"
        ),
        "research/reviews/protocol-decision.json": (
            "1d9e3a7fe69ca330571abbfca469433010a6acfdf7f47a6f788d9cc8349ab474"
        ),
    }
    for path, digest in expected.items():
        assert hashlib.sha256((repository_root / path).read_bytes()).hexdigest() == digest
    assert registry()["phase_13_ready"] is False
    verification = (repository_root / "docs/phase-12.8f-verification.md").read_text()
    assert "37643825730" in verification and "not imported" in verification
    failed = json.loads(
        (repository_root / "research/evidence/phase-12.8f-failed-run-37643825730.json").read_text()
    )
    supplied = failed.pop("fingerprint")
    from archguard.domain.orchestration import fingerprint

    assert supplied == fingerprint(failed)
    assert failed["qualified_tasks"] == 0 and failed["imported"] is False
    diagnostic = json.loads(
        (repository_root / "research/evidence/phase-12.8f-run-37672954475.json").read_text()
    )
    supplied = diagnostic.pop("fingerprint")
    assert supplied == fingerprint(diagnostic)
    assert diagnostic["qualified_tasks"] == 0 and diagnostic["imported"] is False


def test_imported_pysnooper_one_non_reproducibility_is_preserved(
    repository_root: Path,
) -> None:
    imported = json.loads(
        (repository_root / "research/evidence/phase-12.8f-qualification.json").read_text()
    )
    assert imported["fingerprint"] == (
        "477bc32a8302e2892293f9b533062715745d943fe198d541f7cacdfbda1c3606"
    )
    assert imported["archive_sha256"] == (
        "03dceada05ba317478a2392729912dd381a24e5c77728ffaae0b4be5c2aae9f5"
    )
    assert imported["manifest"]["github_run_id"] == "38147331854"
    assert imported["phase_13_ready"] is False
    result = imported["qualification"]["results"][0]
    assert result["task_id"] == "PySnooper-1"
    assert result["classification"] == "NOT_REPRODUCIBLE"
    assert result["qualification_decision"] == "NOT_QUALIFIED"
    assert [attempt["outcome"] for attempt in result["buggy_attempts"]] == ["PASS"] * 3
    assert [attempt["tests_passed"] for attempt in result["buggy_attempts"]] == [1] * 3
    assert result["fixed_control_passed"] is False
    assert result["fixed_control"]["attempted"] is False


def test_imported_remaining_qualification_is_preserved(repository_root: Path) -> None:
    imported = json.loads(
        (repository_root / "research/evidence/phase-12.8f-remaining-qualification.json").read_text()
    )
    assert imported["fingerprint"] == (
        "f975e236f0394bcf0138073919119c2df4f2f3d9961abdc781c18d6b2721f7c1"
    )
    assert imported["archive_sha256"] == (
        "f802a552d53345208084e34b3a39b563019f0f9d71eebbaf03a19522819be001"
    )
    assert imported["manifest"]["github_run_id"] == "38149905317"
    assert imported["phase_13_ready"] is False
    results = {result["task_id"]: result for result in imported["qualification"]["results"]}
    pysnooper = results["PySnooper-3"]
    assert (pysnooper["classification"], pysnooper["qualification_decision"]) == (
        "STABLE",
        "QUALIFIED",
    )
    attempts = results["PySnooper-3"]["buggy_attempts"]
    assert [attempt["outcome"] for attempt in attempts] == ["EXPECTED_FAILURE"] * 3
    assert len({attempt["failure_signature"] for attempt in attempts}) == 1
    assert results["PySnooper-3"]["fixed_control_passed"] is True
    assert results["black-1"]["classification"] == "EVALUATOR_ENVIRONMENT_INVALID"
    assert results["black-1"]["qualification_decision"] == "NOT_QUALIFIED"
    assert results["cookiecutter-4"]["classification"] == "EVALUATOR_ENVIRONMENT_INVALID"
    assert results["cookiecutter-4"]["qualification_decision"] == "NOT_QUALIFIED"
