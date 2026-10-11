import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from archguard.domain.phase128f import BATCH_A, AttemptEvidence, EvaluatorRuntimeState, Outcome
from scripts import phase128f_runner as runner
from scripts.phase128f_registry import adapters
from scripts.phase128f_security_scan import scan

REAL_PREPARE_EVALUATOR_FIXTURE = runner._prepare_evaluator_fixture
REAL_EXECUTION_PLAN = runner._execution_plan
REAL_PREFLIGHT = runner._preflight
REAL_VERIFY_SOURCE_UNCHANGED = runner._verify_source_unchanged
REAL_VERIFY_EVALUATOR_IDENTITY = runner._verify_evaluator_identity


@pytest.fixture(autouse=True)
def reviewed_fixture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fixture = tmp_path / "reviewed-evaluator.py"
    fixture.write_bytes(b"")
    monkeypatch.setattr(runner, "_prepare_evaluator_fixture", lambda *args: fixture)
    monkeypatch.setattr(
        runner,
        "_execution_plan",
        lambda *args: {"host_fixture_fingerprint": "a" * 64, "v3_plan_validation": "VALID"},
    )

    def preflight(*args: Any) -> dict[str, Any]:
        transitions = args[-1] if isinstance(args[-1], runner.RuntimeTransitions) else None
        if transitions is not None:
            for state in (
                EvaluatorRuntimeState.TMPFS_CREATED,
                EvaluatorRuntimeState.WRITABLE_PATHS_VERIFIED,
                EvaluatorRuntimeState.SOURCE_MOUNTED,
                EvaluatorRuntimeState.EVALUATOR_MOUNTED,
                EvaluatorRuntimeState.PROJECT_IMPORT_VERIFIED,
                EvaluatorRuntimeState.EVALUATOR_IMPORT_VERIFIED,
                EvaluatorRuntimeState.TEST_COLLECTED,
            ):
                transitions.reach(state, {"test": True})
        return {
            "collection_count": 1,
            "container_visible_fixture_fingerprint": "a" * 64,
            "evaluator_fixture_mounted": True,
            "evaluator_fixture_identity_match": True,
            "project_installation_preflight": "PASSED",
        }

    monkeypatch.setattr(runner, "_preflight", preflight)
    monkeypatch.setattr(runner, "_verify_source_unchanged", lambda *args: None)
    monkeypatch.setattr(runner, "_verify_evaluator_identity", lambda *args: "a" * 64)


def _identity(revision: str, marker: str = "a") -> dict[str, Any]:
    return {
        "requested_revision": revision,
        "acquired_repository_revision": revision,
        "checked_out_head": revision,
        "git_tree_identity": marker * 40,
        "working_directory_fingerprint": marker * 64,
        "container_visible_source_fingerprint": marker * 64,
        "build_context_fingerprint": "c" * 64,
    }


def _checkout_identity(repository: str, revision: str, destination: Path) -> dict[str, Any]:
    marker = "a" if destination.name == "buggy" else "b"
    return _identity(revision, marker)


def test_source_immutability_check_rejects_changed_tree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner, "_verify_source_unchanged", REAL_VERIFY_SOURCE_UNCHANGED)
    source = tmp_path / "source"
    source.mkdir()
    (source / "tracked.py").write_text("before\n")
    identity = {"working_directory_fingerprint": runner._working_tree_fingerprint(source)}
    (source / "tracked.py").write_text("after\n")
    with pytest.raises(RuntimeError, match="source tree changed"):
        runner._verify_source_unchanged(source, identity)


def test_structured_evaluator_argv_and_selector_are_separate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 1, b"1 failed", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(runner, "_container_source_fingerprint", lambda *args: "a" * 64)
    adapter = adapters()[0]
    source = tmp_path / "source"
    source.mkdir()
    fixture = tmp_path / "evaluator/tests/test_chinese.py"
    fixture.parent.mkdir(parents=True)
    fixture.write_bytes(b"")
    runner._execute(
        adapter,
        "image",
        source,
        "attempt",
        expected_outcome="TEST_FAILURE",
        source_identity=_identity(adapter.buggy_revision),
        evaluator_fixture=fixture,
    )
    command = calls[0]
    marker = command.index("python")
    assert command[marker:] == [
        "python",
        "-m",
        "pytest",
        "-q",
        "-s",
        "-o",
        "cache_dir=/tmp/pytest-cache",
        "/evaluator/tests/test_chinese.py::test_chinese",
    ]
    assert "python -m pytest -q -s" not in command


def test_absent_base_image_is_pulled_and_linux_amd64_verified(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commands: list[list[str]] = []
    details = [
        {
            "Architecture": "amd64",
            "Id": "sha256:" + "a" * 64,
            "Os": "linux",
            "RepoDigests": ["python@sha256:" + "b" * 64],
            "RepoTags": ["python:3.8.1"],
            "Size": 123,
        }
    ]

    def fake_subprocess(command: list[str], **_: Any) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(command, 1, b"", b"")

    def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[bytes]:
        commands.append(command)
        stdout = (
            json.dumps(details).encode() if command[:3] == ["docker", "image", "inspect"] else b""
        )
        return subprocess.CompletedProcess(command, 0, stdout, b"")

    runner.OWNED_BASE_REFERENCES.clear()
    monkeypatch.setattr(subprocess, "run", fake_subprocess)
    monkeypatch.setattr(runner, "_run", fake_run)
    reference, identity, size = runner._acquire_base_image(adapters()[0], tmp_path)
    assert commands[0] == ["docker", "pull", "--platform", "linux/amd64", "python:3.8.1"]
    assert reference == "archguard-phase128f-base-3.8.1" and size == 123
    assert identity["architecture"] == "amd64" and identity["operating_system"] == "linux"
    assert "python:3.8.1" in runner.OWNED_BASE_REFERENCES


def test_base_image_wrong_architecture_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    details = [{"Architecture": "arm64", "Os": "linux", "RepoTags": ["python:3.8.1"]}]
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, b"", b""),
    )
    monkeypatch.setattr(
        runner,
        "_run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 0, json.dumps(details).encode(), b""
        ),
    )
    with pytest.raises(RuntimeError, match="platform"):
        runner._acquire_base_image(adapters()[0], tmp_path)


def test_base_acquisition_failure_has_stage_and_does_not_conflict_prior(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner, "_safe_checkout", _checkout_identity)
    monkeypatch.setattr(runner, "_verify_identities", lambda *args: None)
    monkeypatch.setattr(
        runner,
        "_acquire_base_image",
        lambda adapter, build_root: (_ for _ in ()).throw(
            subprocess.CalledProcessError(1, ["docker", "pull"], stderr=b"registry unavailable")
        ),
    )
    result = runner.qualify(adapters()[0], tmp_path, tmp_path)
    assert result["classification"] == "INFRASTRUCTURE_FAILURE"
    assert result["scientific_classification"] is None
    assert result["prior_evidence_status"] == "NOT_EVALUATED_INFRASTRUCTURE_FAILURE"
    assert result["infrastructure_diagnostic"]["failure_stage"] == "BASE_IMAGE_ACQUISITION"
    assert result["infrastructure_diagnostic"]["failure_code"] == ("BASE_IMAGE_ACQUISITION_FAILED")
    assert all(item["duration_milliseconds"] == 0 for item in result["buggy_attempts"])
    assert "registry unavailable" not in json.dumps(result)


def test_security_scanner_canary_missing_input_and_utf8(tmp_path: Path) -> None:
    canary = tmp_path / "canary.json"
    canary.write_text('{"raw_log":"forbidden"}', encoding="utf-8")
    with pytest.raises(ValueError, match="forbidden"):
        scan((canary,))
    with pytest.raises(ValueError, match="missing"):
        scan((tmp_path / "missing-scanner-input.json",))
    binary = tmp_path / "binary.json"
    binary.write_bytes(b"\xff")
    with pytest.raises(ValueError, match="non-UTF-8"):
        scan((binary,))


def test_cleanup_removes_only_labeled_and_newly_pulled_images(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[bytes]:
        commands.append(command)
        stdout = b"owned-id\n" if command[1:3] == ["images", "-q"] else b""
        return subprocess.CompletedProcess(command, 0, stdout, b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner.OWNED_BASE_REFERENCES.clear()
    runner.OWNED_BASE_REFERENCES.add("python:3.8.1")
    root = tmp_path / "owned"
    root.mkdir()
    runner.cleanup(root)
    assert ["docker", "image", "rm", "-f", "owned-id"] in commands
    assert ["docker", "image", "rm", "python:3.8.1"] in commands
    assert not root.exists()
    assert not runner.OWNED_BASE_REFERENCES


def _run_with_fixed_attempt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fixed: AttemptEvidence,
    adapter_index: int = 1,
) -> dict[str, Any]:
    buggy = AttemptEvidence(
        Outcome.EXPECTED_FAILURE,
        1,
        "a" * 64,
        0,
        1,
        100,
        normalized_failure_class="TEST_FAILURE",
    )
    attempts = iter((buggy, buggy, buggy, fixed))
    monkeypatch.setattr(runner, "_safe_checkout", _checkout_identity)
    monkeypatch.setattr(runner, "_verify_identities", lambda *args: None)
    monkeypatch.setattr(
        runner,
        "_acquire_base_image",
        lambda *args: (
            "base",
            {
                "architecture": "amd64",
                "image_id": "sha256:" + "b" * 64,
                "operating_system": "linux",
            },
            10,
        ),
    )
    monkeypatch.setattr(
        runner,
        "_build_image",
        lambda *args: (
            "image",
            [{"filename": "dependency.whl", "sha256": "c" * 64}],
            20,
            {
                "build_context_fingerprint": "c" * 64,
                "image_id": "sha256:" + "d" * 64,
                "source_in_image": "ABSENT_DEPENDENCY_ONLY",
                "tag": "image",
            },
        ),
    )
    monkeypatch.setattr(runner, "_execute", lambda *args, **kwargs: next(attempts))
    return runner.qualify(adapters()[adapter_index], tmp_path, tmp_path)


def test_fixed_control_passes_with_bound_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixed = AttemptEvidence(Outcome.PASS, 0, None, 1, 0, 100)
    result = _run_with_fixed_attempt(monkeypatch, tmp_path, fixed)
    assert result["classification"] == "STABLE"
    assert result["qualification_decision"] == "QUALIFIED"
    assert result["fixed_control"]["outcome"] == "PASS"
    assert (
        result["fixed_control"]["dependency_environment_fingerprint"]
        == (result["buggy_environment_fingerprint"])
    )
    assert result["runtime_state_machine"]["last_reached"] == "CLEANED"
    assert result["runtime_state_machine"]["next_required"] is None


def test_pysnooper_one_canary_qualifies_only_after_complete_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixed = AttemptEvidence(Outcome.PASS, 0, None, 1, 0, 100)
    result = _run_with_fixed_attempt(monkeypatch, tmp_path, fixed, adapter_index=0)
    assert result["qualification_decision"] == "QUALIFIED"
    assert result["prior_evidence_status"] == "PRIOR_EVALUATOR_NOT_COMPARABLE"
    assert result["runtime_state_machine"]["next_required"] is None


@pytest.mark.parametrize(
    ("fixed", "classification", "stage"),
    [
        (
            AttemptEvidence(
                Outcome.OTHER_FAILURE,
                1,
                "e" * 64,
                0,
                1,
                100,
                normalized_failure_class="ASSERTION_FAILURE",
            ),
            "FIXED_CONTROL_FAILED",
            "TEST_EXECUTION",
        ),
        (
            AttemptEvidence(
                Outcome.OTHER_FAILURE,
                2,
                "f" * 64,
                0,
                0,
                100,
                normalized_failure_class="COLLECTION_ERROR",
            ),
            "FIXED_CONTROL_FAILED",
            "TEST_COLLECTION",
        ),
        (
            AttemptEvidence(
                Outcome.TIMEOUT,
                None,
                None,
                0,
                0,
                1_200_000,
                True,
                "TIMEOUT",
            ),
            "FIXED_CONTROL_INFRASTRUCTURE_FAILURE",
            "TEST_EXECUTION",
        ),
    ],
)
def test_fixed_failure_is_not_false_environment_sensitive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fixed: AttemptEvidence,
    classification: str,
    stage: str,
) -> None:
    result = _run_with_fixed_attempt(monkeypatch, tmp_path, fixed)
    assert result["classification"] == classification
    assert result["scientific_classification"] is None
    assert result["qualification_decision"] == "NOT_QUALIFIED"
    assert result["fixed_control"]["stage"] == stage


@pytest.mark.parametrize(
    ("failure_stage", "expected_stage"),
    [("DEPENDENCY_BUILD", "DEPENDENCY_RESOLUTION"), ("PROJECT_INSTALL", "PROJECT_INSTALL")],
)
def test_pre_fixed_failure_stage_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure_stage: str,
    expected_stage: str,
) -> None:
    monkeypatch.setattr(runner, "_safe_checkout", _checkout_identity)
    monkeypatch.setattr(runner, "_verify_identities", lambda *args: None)
    monkeypatch.setattr(
        runner,
        "_acquire_base_image",
        lambda *args: (
            "base",
            {
                "architecture": "amd64",
                "image_id": "sha256:" + "b" * 64,
                "operating_system": "linux",
            },
            10,
        ),
    )
    if failure_stage == "DEPENDENCY_BUILD":
        monkeypatch.setattr(
            runner,
            "_build_image",
            lambda *args: (_ for _ in ()).throw(RuntimeError("build failed")),
        )
    else:
        monkeypatch.setattr(
            runner,
            "_build_image",
            lambda *args: (
                "image",
                [],
                20,
                {
                    "build_context_fingerprint": "c" * 64,
                    "image_id": "id",
                    "source_in_image": "ABSENT_DEPENDENCY_ONLY",
                    "tag": "image",
                },
            ),
        )
        monkeypatch.setattr(
            runner,
            "_prepare_project",
            lambda *args: (_ for _ in ()).throw(RuntimeError("install failed")),
        )
    result = runner.qualify(adapters()[0], tmp_path, tmp_path)
    assert result["fixed_control"]["attempted"] is False
    assert result["fixed_control"]["stage"] == expected_stage
    assert result["infrastructure_diagnostic"]["failure_stage"] == failure_stage


def test_absent_fixed_revision_is_acquisition_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = 0

    def checkout(*args: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise subprocess.CalledProcessError(128, ["git", "checkout"], stderr=b"missing")

    monkeypatch.setattr(runner, "_safe_checkout", checkout)
    result = runner.qualify(adapters()[0], tmp_path, tmp_path)
    assert result["fixed_control"]["stage"] == "ACQUISITION"
    assert result["fixed_control"]["attempted"] is False
    assert result["qualification_decision"] == "NOT_QUALIFIED"


def test_normalized_signature_is_deterministic_and_output_is_bounded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    outputs = iter(
        (
            b"FAILED /tmp/one/test.py after 1.23s\n",
            b"FAILED /tmp/two/test.py after 9.87s\n",
        )
    )

    def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[bytes]:
        if command[:3] == ["docker", "rm", "-f"]:
            return subprocess.CompletedProcess(command, 0, b"", b"")
        return subprocess.CompletedProcess(command, 1, next(outputs), b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(runner, "_container_source_fingerprint", lambda *args: "a" * 64)
    adapter = adapters()[0]
    identity = _identity(adapter.buggy_revision)
    source = tmp_path / "source"
    source.mkdir()
    fixture = tmp_path / "evaluator/tests/test_chinese.py"
    fixture.parent.mkdir(parents=True)
    fixture.write_bytes(b"")
    first = runner._execute(
        adapter,
        "image",
        source,
        "one",
        expected_outcome="TEST_FAILURE",
        source_identity=identity,
        evaluator_fixture=fixture,
    )
    second = runner._execute(
        adapter,
        "image",
        source,
        "two",
        expected_outcome="TEST_FAILURE",
        source_identity=identity,
        evaluator_fixture=fixture,
    )
    assert first.failure_signature == second.failure_signature

    oversized = b"x" * (adapter.sandbox.output_bytes + 1)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 1, oversized, b""),
    )
    bounded = runner._execute(
        adapter,
        "image",
        source,
        "bounded",
        expected_outcome="TEST_FAILURE",
        source_identity=identity,
        evaluator_fixture=fixture,
    )
    assert bounded.output_truncated is True


def test_failure_categories_distinguish_selector_collection_and_assertion() -> None:
    assert runner._failure_category("collected 0 items", 4) == "SELECTOR_NOT_FOUND"
    assert runner._failure_category("ERROR collecting test_module.py", 2) == "COLLECTION_ERROR"
    assert (
        runner._failure_category("FAILED test_module.py AssertionError", 1) == "ASSERTION_FAILURE"
    )


def test_fixed_expected_failure_is_rejected() -> None:
    adapter = adapters()[0]
    attempt = AttemptEvidence(
        Outcome.EXPECTED_FAILURE, 1, "a" * 64, 0, 1, 1, normalized_failure_class="ASSERTION_FAILURE"
    )
    with pytest.raises(RuntimeError, match="cannot have EXPECTED_FAILURE"):
        runner._fixed_control_record(
            adapter, attempt, "c" * 64, {}, _identity(adapter.fixed_revision)
        )


def test_container_source_identity_mismatch_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    adapter = adapters()[0]
    monkeypatch.setattr(runner, "_container_source_fingerprint", lambda *args: "b" * 64)
    with pytest.raises(RuntimeError, match="container-visible source identity mismatch"):
        runner._execute(
            adapter,
            "image",
            tmp_path,
            "mismatch",
            expected_outcome="EXIT_ZERO",
            source_identity=_identity(adapter.fixed_revision),
        )


def test_quarantined_evaluator_is_mounted_read_only_for_both_expectations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(runner, "_container_source_fingerprint", lambda *args: "a" * 64)

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, b"1 passed", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    adapter = adapters()[0]
    source = tmp_path / "source"
    source.mkdir()
    fixture = tmp_path / "quarantine/tests/test_chinese.py"
    fixture.parent.mkdir(parents=True)
    fixture.write_bytes(b"")
    for expectation in ("TEST_FAILURE", "EXIT_ZERO"):
        runner._execute(
            adapter,
            "image",
            source,
            expectation.lower(),
            expected_outcome=expectation,
            source_identity=_identity(adapter.buggy_revision),
            evaluator_fixture=fixture,
        )
    evaluator_mount = f"{tmp_path / 'quarantine'}:/evaluator:ro"
    execution_calls = [call for call in calls if evaluator_mount in call]
    assert len(execution_calls) == 2
    assert all(
        "--network" in call and call[call.index("--network") + 1] == "none"
        for call in execution_calls
    )


def test_unittest_selector_uses_explicit_fixture_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner, "_prepare_evaluator_fixture", REAL_PREPARE_EVALUATOR_FIXTURE)
    adapter = next(item for item in adapters() if item.task_id == "black-1")
    assert adapter.test_selectors == (
        "tests.test_black.BlackTestCase.test_works_in_mono_process_only_environment",
    )
    assert adapter.evaluator_fixture_path == "tests/test_black.py"

    fixed = tmp_path / "fixed"
    source = fixed / "tests/test_black.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"reviewed evaluator")
    quarantine = tmp_path / "quarantine"

    expected_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    reviewed = replace(adapter, evaluator_fixture_sha256=expected_hash, fingerprint="")
    fixture = runner._prepare_evaluator_fixture(reviewed, fixed, quarantine)

    assert fixture == quarantine / "tests/test_black.py"
    assert fixture.read_bytes() == source.read_bytes()
    assert (quarantine / "tests/__init__.py").is_file()
    assert not (fixed / "tests/__init__.py").exists()


def test_every_v3_field_has_runtime_consumer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner, "_execution_plan", REAL_EXECUTION_PLAN)
    adapter = adapters()[0]
    fixture = tmp_path / "quarantine/tests/test_chinese.py"
    fixture.parent.mkdir(parents=True)
    fixture.write_bytes(b"fixture")
    reviewed = replace(
        adapter,
        evaluator_fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
        fingerprint="",
    )
    plan = runner._execution_plan(reviewed, fixture)
    assert set(plan["runtime_consumers"]) == set(runner.V3_RUNTIME_FIELDS)
    assert plan["v3_plan_validation"] == "VALID"


def test_invalid_quarantine_policy_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner, "_execution_plan", REAL_EXECUTION_PLAN)
    fixture = tmp_path / "quarantine/tests/test_chinese.py"
    fixture.parent.mkdir(parents=True)
    fixture.write_bytes(b"fixture")
    adapter = replace(
        adapters()[0],
        quarantine_policy="NONE",
        evaluator_fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
        fingerprint="",
    )
    with pytest.raises(runner.EvaluatorPreflightError, match="QUARANTINE_POLICY_INVALID"):
        runner._execution_plan(adapter, fixture)


def test_nested_evaluator_mount_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source"
    evaluator = source / "evaluator"
    evaluator.mkdir(parents=True)
    with pytest.raises(runner.EvaluatorPreflightError, match="INVALID_NESTED_EVALUATOR_MOUNT"):
        runner._sandbox_prefix(adapters()[0], "image", source, evaluator, "nested")


def test_tox_runtime_is_offline_and_uses_reviewed_environment(tmp_path: Path) -> None:
    adapter = next(item for item in adapters() if item.task_id == "cookiecutter-4")
    source = tmp_path / "source"
    evaluator = tmp_path / "evaluator"
    source.mkdir()
    evaluator.mkdir()
    command = runner._sandbox_prefix(adapter, "image", source, evaluator, "tox")
    command += list(runner._runtime_argv(adapter, "TEST_FAILURE"))
    assert command[command.index("--network") + 1] == "none"
    assert "PIP_NO_INDEX=1" in command and "PIP_FIND_LINKS=/wheelhouse" in command
    assert command[-4:] == [
        "-e",
        "py36",
        "--",
        "/evaluator/tests/test_hooks.py::TestExternalHooks::test_run_failing_hook",
    ]


def test_batch_b_is_unavailable() -> None:
    with pytest.raises(ValueError, match="Batch B"):
        runner._tasks("batch-b")


@pytest.mark.parametrize("tasks", [("PySnooper-3",), ("black-1",), ("cookiecutter-4",)])
def test_runtime_canary_rejects_every_other_task(tasks: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="only PySnooper-1"):
        runner._validate_runtime_canary_selection(tasks)


def test_docker_exit_125_is_infrastructure_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner, "_safe_checkout", _checkout_identity)
    monkeypatch.setattr(runner, "_verify_identities", lambda *args: None)
    monkeypatch.setattr(
        runner,
        "_acquire_base_image",
        lambda *args: ("base", {"architecture": "amd64", "image_id": "id"}, 1),
    )
    monkeypatch.setattr(
        runner,
        "_build_image",
        lambda *args: (
            "image",
            [],
            1,
            {
                "build_context_fingerprint": "c" * 64,
                "image_id": "id",
                "source_in_image": "ABSENT_DEPENDENCY_ONLY",
                "tag": "image",
            },
        ),
    )
    monkeypatch.setattr(
        runner,
        "_execute",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            subprocess.CalledProcessError(125, ["docker", "run"], stderr=b"mount rejected")
        ),
    )
    result = runner.qualify(adapters()[0], tmp_path, tmp_path)
    assert result["classification"] == "INFRASTRUCTURE_FAILURE"
    assert result["scientific_classification"] is None
    assert result["infrastructure_diagnostic"]["process_return_code"] == 125


def test_collection_failure_retains_only_source_free_process_diagnostic(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner, "_safe_checkout", _checkout_identity)
    monkeypatch.setattr(runner, "_verify_identities", lambda *args: None)
    monkeypatch.setattr(
        runner,
        "_acquire_base_image",
        lambda *args: ("base", {"architecture": "amd64", "image_id": "id"}, 1),
    )
    monkeypatch.setattr(
        runner,
        "_build_image",
        lambda *args: (
            "image",
            [],
            1,
            {
                "build_context_fingerprint": "c" * 64,
                "image_id": "id",
                "source_in_image": "ABSENT_DEPENDENCY_ONLY",
                "tag": "image",
            },
        ),
    )
    monkeypatch.setattr(
        runner,
        "_preflight",
        lambda *args: (_ for _ in ()).throw(
            runner.EvaluatorPreflightError("EVALUATOR_SELECTOR_NOT_FOUND", 4)
        ),
    )
    result = runner.qualify(adapters()[0], tmp_path, tmp_path)
    diagnostic = result["infrastructure_diagnostic"]
    assert diagnostic["process_return_code"] == 4
    assert diagnostic["failure_code"] == "EVALUATOR_SELECTOR_NOT_FOUND"
    assert "raw_log" not in json.dumps(result)


def test_offline_dependency_absence_is_non_scientific(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner, "_safe_checkout", _checkout_identity)
    monkeypatch.setattr(runner, "_verify_identities", lambda *args: None)
    monkeypatch.setattr(
        runner,
        "_acquire_base_image",
        lambda *args: ("base", {"architecture": "amd64", "image_id": "id"}, 1),
    )
    monkeypatch.setattr(
        runner,
        "_build_image",
        lambda *args: (
            "image",
            [],
            1,
            {
                "build_context_fingerprint": "c" * 64,
                "image_id": "id",
                "source_in_image": "ABSENT_DEPENDENCY_ONLY",
                "tag": "image",
            },
        ),
    )
    monkeypatch.setattr(
        runner,
        "_preflight",
        lambda *args: (_ for _ in ()).throw(
            runner.EvaluatorPreflightError("OFFLINE_DEPENDENCY_MISSING")
        ),
    )
    cookiecutter = next(item for item in adapters() if item.task_id == "cookiecutter-4")
    result = runner.qualify(cookiecutter, tmp_path, tmp_path)
    assert result["classification"] == "EVALUATOR_ENVIRONMENT_INVALID"
    assert result["scientific_classification"] is None
    assert result["evaluator_validation_status"] == "OFFLINE_DEPENDENCY_MISSING"


def test_configured_but_absent_runtime_fixture_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner, "_verify_evaluator_identity", REAL_VERIFY_EVALUATOR_IDENTITY)
    with pytest.raises(runner.EvaluatorPreflightError, match="EVALUATOR_NOT_ACQUIRED"):
        runner._verify_evaluator_identity(adapters()[0], tmp_path / "absent.py")


def test_wrong_evaluator_hash_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner, "_verify_evaluator_identity", REAL_VERIFY_EVALUATOR_IDENTITY)
    fixture = tmp_path / "fixture.py"
    fixture.write_bytes(b"wrong")
    with pytest.raises(runner.EvaluatorPreflightError, match="EVALUATOR_IDENTITY_MISMATCH"):
        runner._verify_evaluator_identity(adapters()[0], fixture)


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("source_exists", "MOUNT_PROBE_SOURCE_EXISTS"),
        ("evaluator_exists", "MOUNT_PROBE_EVALUATOR_EXISTS"),
        ("fixture_exists", "MOUNT_PROBE_FIXTURE_EXISTS"),
        ("mounts_distinct", "MOUNT_PROBE_MOUNTS_DISTINCT"),
    ],
)
def test_mount_probe_rejects_missing_or_wrong_topology(field: str, code: str) -> None:
    probe = {
        "source_exists": True,
        "evaluator_exists": True,
        "fixture_exists": True,
        "fixture_sha256": "a" * 64,
        "mounts_distinct": True,
        "source_read_only": True,
        "evaluator_read_only": True,
        "temporary_writable": True,
        "home_writable": True,
        "docker_socket_absent": True,
        "network_disabled": True,
    }
    probe[field] = False
    with pytest.raises(runner.EvaluatorPreflightError, match=code):
        runner._validate_mount_probe(probe, "a" * 64)


def test_mount_probe_rejects_wrong_container_visible_fixture_hash() -> None:
    probe = {
        "source_exists": True,
        "evaluator_exists": True,
        "fixture_exists": True,
        "fixture_sha256": "b" * 64,
        "mounts_distinct": True,
        "source_read_only": True,
        "evaluator_read_only": True,
        "docker_socket_absent": True,
        "network_disabled": True,
    }
    with pytest.raises(runner.EvaluatorPreflightError, match="EVALUATOR_IDENTITY_MISMATCH"):
        runner._validate_mount_probe(probe, "a" * 64)


def test_project_import_plan_is_explicit_and_source_backed() -> None:
    prepared = runner._prepare_project(adapters()[0])
    assert prepared["installation_mode"] == "PYTHONPATH_SOURCE"
    assert prepared["module_name_fingerprint"] == runner._sha256_record("pysnooper")


def test_generic_project_import_name_is_rejected() -> None:
    adapter = replace(adapters()[0], project="project", fingerprint="")
    with pytest.raises(runner.EvaluatorPreflightError, match="PROJECT_MODULE_NOT_ALLOWLISTED"):
        runner._prepare_project(adapter)


@pytest.mark.parametrize("output", ["no tests ran", "2 tests collected"])
def test_collection_requires_exactly_one_selected_test(output: str) -> None:
    with pytest.raises(runner.EvaluatorPreflightError, match="EVALUATOR_NOT_COLLECTED"):
        runner._validate_pytest_collection(output, "tests/test_chinese.py::test_chinese")


def test_compact_pytest_collection_node_is_normalized() -> None:
    logical = "tests/test_chinese.py::test_chinese"
    assert runner._validate_pytest_collection("::test_chinese\n", logical) == (1, logical)


def test_runtime_state_machine_rejects_skipped_transition() -> None:
    transitions = runner.RuntimeTransitions()
    with pytest.raises(runner.EvaluatorPreflightError, match="MISSING_TRANSITION_PLAN_VALIDATED"):
        transitions.reach(EvaluatorRuntimeState.SOURCE_ACQUIRED, {"operation": True})


def _writable_probe() -> dict[str, Any]:
    return {
        "tmpfs_created": True,
        "writable_paths": [
            {
                "cleanup": True,
                "exists": True,
                "mount_type_category": "tmpfs",
                "not_symlink": True,
                "outside_protected_mounts": True,
                "ownership_compatible": True,
                "role_fingerprint": hashlib.sha256(role.encode()).hexdigest(),
                "writable": True,
            }
            for role in ("temporary-root", "home", "temporary-data", "pytest-cache")
        ],
    }


@pytest.mark.parametrize(
    ("index", "field", "code"),
    [
        (1, "exists", "WRITABLE_PROBE_EXISTS"),
        (2, "exists", "WRITABLE_PROBE_EXISTS"),
        (0, "ownership_compatible", "WRITABLE_PROBE_OWNERSHIP_COMPATIBLE"),
        (1, "ownership_compatible", "WRITABLE_PROBE_OWNERSHIP_COMPATIBLE"),
        (2, "not_symlink", "WRITABLE_PROBE_NOT_SYMLINK"),
        (3, "cleanup", "WRITABLE_PROBE_CLEANUP"),
        (0, "outside_protected_mounts", "WRITABLE_PROBE_OUTSIDE_PROTECTED_MOUNTS"),
        (1, "outside_protected_mounts", "WRITABLE_PROBE_OUTSIDE_PROTECTED_MOUNTS"),
    ],
)
def test_writable_probe_fails_closed(index: int, field: str, code: str) -> None:
    probe = _writable_probe()
    probe["writable_paths"][index][field] = False
    with pytest.raises(runner.EvaluatorPreflightError, match=code):
        runner._validate_writable_probe(probe)


def test_writable_probe_requires_created_tmpfs_and_accepts_noexec(tmp_path: Path) -> None:
    with pytest.raises(runner.EvaluatorPreflightError, match="TMPFS_NOT_CREATED"):
        runner._validate_tmpfs_created({"tmpfs_created": False})
    probe = _writable_probe()
    runner._validate_tmpfs_created(probe)
    runner._validate_writable_probe(probe)
    source = tmp_path / "source"
    evaluator = tmp_path / "evaluator"
    source.mkdir()
    evaluator.mkdir()
    command = runner._sandbox_prefix(adapters()[0], "image", source, evaluator, "probe")
    tmpfs = command[command.index("--tmpfs") + 1]
    assert "noexec" in tmpfs and "mode=1777" in tmpfs


def test_runtime_never_executes_probe_and_relocates_python_and_pytest_writes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    evaluator = tmp_path / "evaluator"
    source.mkdir()
    evaluator.mkdir()
    command = runner._sandbox_prefix(adapters()[0], "image", source, evaluator, "probe")
    assert "PYTHONDONTWRITEBYTECODE=1" in command
    assert "PYTHONPYCACHEPREFIX=/tmp/archguard/pycache" in command
    assert "HOME=/tmp/home" in command and "TMPDIR=/tmp/archguard" in command
    assert all("chmod" not in str(value) for value in runner._mount_probe.__code__.co_consts)
    runtime = runner._runtime_argv(adapters()[0], "TEST_FAILURE")
    assert "cache_dir=/tmp/pytest-cache" in runtime


def test_canary_rejects_batch_a_and_batch_b() -> None:
    with pytest.raises(ValueError, match="only PySnooper-1"):
        runner._validate_runtime_canary_selection(BATCH_A)
    with pytest.raises(ValueError, match="Batch B"):
        runner._tasks("batch-b")


def test_mount_probe_failure_always_cleans_container(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def failed_probe(command: list[str], **_: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 1, b"", b"")

    source = tmp_path / "source"
    evaluator = tmp_path / "evaluator"
    source.mkdir()
    evaluator.mkdir()
    monkeypatch.setattr(subprocess, "run", failed_probe)
    with pytest.raises(runner.EvaluatorPreflightError, match="MOUNT_PROBE_FAILED"):
        runner._mount_probe(adapters()[0], "image", source, evaluator, "failed-probe")
    assert calls[-1] == ["docker", "rm", "-f", "failed-probe"]


def test_pytest_standalone_fixture_uses_external_selector_without_package_import() -> None:
    adapter = adapters()[0]
    resolution = runner._resolve_external_pytest_selector(
        adapter.buggy_test_selectors[0],
        adapter.evaluator_fixture_path or "",
        "/evaluator",
        adapter.expected_framework,
    )
    assert resolution.logical_selector == "tests/test_chinese.py::test_chinese"
    assert resolution.physical_fixture == "/evaluator/tests/test_chinese.py"
    assert resolution.runtime_selector == "/evaluator/tests/test_chinese.py::test_chinese"
    assert runner._runtime_selectors(adapter, "TEST_FAILURE") == (
        "/evaluator/tests/test_chinese.py::test_chinese",
    )
    assert "tests.test_chinese" not in runner._runtime_argv(adapter, "TEST_FAILURE")


@pytest.mark.parametrize(
    "selector",
    (
        "/workspace/tests/test_chinese.py::test_chinese",
        "../tests/test_chinese.py::test_chinese",
        "/tmp/test_chinese.py::test_chinese",
        "tests/other.py::test_chinese",
        "tests/tests/test_chinese.py::test_chinese",
        "tests/test_chinese.py::",
    ),
)
def test_external_selector_cannot_escape_evaluator_root(selector: str) -> None:
    adapter = adapters()[0]
    with pytest.raises(runner.EvaluatorPreflightError, match="EVALUATOR_SELECTOR_OUTSIDE_ROOT"):
        runner._resolve_external_pytest_selector(
            selector,
            adapter.evaluator_fixture_path or "",
            "/evaluator",
            adapter.expected_framework,
        )


def test_external_selector_rejects_unverified_mount_root_and_framework() -> None:
    logical = "tests/test_chinese.py::test_chinese"
    for root, framework in (("/workspace", "pytest"), ("/evaluator", "unittest")):
        with pytest.raises(runner.EvaluatorPreflightError, match="OUTSIDE_ROOT"):
            runner._resolve_external_pytest_selector(
                logical, "tests/test_chinese.py", root, framework
            )


def test_execution_plan_binds_selector_identities_without_changing_adapter_fingerprint() -> None:
    adapter = adapters()[0]
    before = adapter.fingerprint
    plan = REAL_EXECUTION_PLAN(adapter)
    resolution = plan["selector_resolutions"][0]
    assert set(resolution) == {
        "logical_selector_fingerprint",
        "physical_fixture_fingerprint",
        "role",
        "runtime_selector_fingerprint",
    }
    assert {item["role"] for item in plan["selector_resolutions"]} == {"buggy", "fixed"}
    assert plan["selector_resolution_fingerprint"] == runner._sha256_record(
        plan["selector_resolutions"]
    )
    assert (
        adapter.fingerprint
        == before
        == "d3a4938e74e6287056a21ab937a167e18c3c8c0e274a719f713068f28e96db10"
    )


def test_collected_node_requires_exactly_the_approved_node() -> None:
    logical = "tests/test_chinese.py::test_chinese"
    assert runner._collected_node(f"{logical}\n1 item collected\n", logical) == logical
    assert runner._collected_node("::test_chinese\n", logical) == logical
    assert runner._collected_node(f"{logical}\n{logical}\n", logical) == logical
    with pytest.raises(runner.EvaluatorPreflightError, match="SELECTED_NODE_MISMATCH"):
        runner._collected_node("tests/test_chinese.py::test_other\n1 item collected\n", logical)
    assert runner._collected_node("::test_chinese\n::test_chinese\n", logical) == logical
    assert runner._collected_node("\x1b[32m::test_chinese\x1b[0m\n", logical) == logical
    with pytest.raises(runner.EvaluatorPreflightError, match="SELECTED_NODE_MISMATCH"):
        runner._collected_node("::test_chinese\n::test_other\n", logical)


def test_pysnooper_evaluator_support_is_identity_checked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner, "_prepare_evaluator_fixture", REAL_PREPARE_EVALUATOR_FIXTURE)
    adapter = adapters()[0]
    fixed = tmp_path / "fixed"
    quarantine = tmp_path / "quarantine"
    fixture = fixed / str(adapter.evaluator_fixture_path)
    fixture.parent.mkdir(parents=True)
    fixture.write_bytes(b"fixture")
    reviewed = replace(
        adapter,
        evaluator_fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
        fingerprint="",
    )
    support = {"tests/__init__.py": b"package", "tests/utils.py": b"helpers"}
    support_hashes = {
        relative: hashlib.sha256(content).hexdigest() for relative, content in support.items()
    }
    monkeypatch.setitem(runner.EVALUATOR_SUPPORT_FILES, adapter.task_id, support_hashes)
    for relative, content in support.items():
        source = fixed / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(content)

    result = runner._prepare_evaluator_fixture(reviewed, fixed, quarantine)

    assert result.read_bytes() == b"fixture"
    for relative, expected_sha256 in support_hashes.items():
        assert hashlib.sha256((quarantine / relative).read_bytes()).hexdigest() == expected_sha256


def test_pysnooper_evaluator_support_mismatch_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner, "_prepare_evaluator_fixture", REAL_PREPARE_EVALUATOR_FIXTURE)
    adapter = adapters()[0]
    fixed = tmp_path / "fixed"
    fixture = fixed / str(adapter.evaluator_fixture_path)
    fixture.parent.mkdir(parents=True)
    fixture.write_bytes(b"fixture")
    support_hashes = {
        "tests/__init__.py": hashlib.sha256(b"expected-package").hexdigest(),
        "tests/utils.py": hashlib.sha256(b"expected-helpers").hexdigest(),
    }
    monkeypatch.setitem(runner.EVALUATOR_SUPPORT_FILES, adapter.task_id, support_hashes)
    for relative in support_hashes:
        source = fixed / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"wrong")
    reviewed = replace(
        adapter,
        evaluator_fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
        fingerprint="",
    )
    with pytest.raises(RuntimeError, match="support identity mismatch"):
        runner._prepare_evaluator_fixture(reviewed, fixed, tmp_path / "quarantine")


@pytest.mark.parametrize(
    ("output", "code"),
    [
        (
            "ERROR: not found: /evaluator/tests/test_chinese.py::missing",
            "EVALUATOR_SELECTOR_NOT_FOUND",
        ),
        ("ImportError while importing test module", "EVALUATOR_DEPENDENCY_MISSING"),
        ("ModuleNotFoundError: No module named dependency", "EVALUATOR_DEPENDENCY_MISSING"),
        ("collection failed", "EVALUATOR_NOT_COLLECTED"),
    ],
)
def test_pytest_collection_failure_is_source_free_and_specific(output: str, code: str) -> None:
    assert runner._pytest_collection_failure_code(output) == code


def test_pytest_collection_distinguishes_target_project_import_error() -> None:
    output = "ImportError while importing pysnooper.tracer"
    assert runner._pytest_collection_failure_code(output, "pysnooper") == "PROJECT_IMPORT_FAILED"


def test_evaluator_import_error_precedes_pytest_selector_not_found_footer() -> None:
    output = (
        "ImportError: attempted relative import with no known parent package\n"
        "ERROR: not found: /evaluator/tests/test_chinese.py::test_chinese\n"
        "no tests ran"
    )
    assert runner._pytest_collection_failure_code(output) == "EVALUATOR_DEPENDENCY_MISSING"


def test_pytest_collection_proves_evaluator_load_then_exact_node(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    adapter = adapters()[0]
    fixture = tmp_path / "evaluator/tests/test_chinese.py"
    fixture.parent.mkdir(parents=True)
    fixture.write_bytes(b"")
    source = tmp_path / "source"
    source.mkdir()
    commands: list[list[str]] = []
    monkeypatch.setattr(runner, "_preflight", REAL_PREFLIGHT)

    monkeypatch.setattr(
        runner,
        "_mount_probe",
        lambda *args: {
            "container_source_fingerprint": "b" * 64,
            "fixture_sha256": adapter.evaluator_fixture_sha256,
            "source_read_only": True,
            "writable_paths": [],
        },
    )
    monkeypatch.setattr(runner, "_validate_tmpfs_created", lambda probe: None)
    monkeypatch.setattr(runner, "_validate_writable_probe", lambda probe: None)
    monkeypatch.setattr(runner, "_validate_mount_probe", lambda probe, digest: None)

    def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[bytes]:
        commands.append(command)
        joined = " ".join(command)
        if "hashlib" in joined:
            return subprocess.CompletedProcess(
                command, 0, f"{adapter.evaluator_fixture_sha256}\n".encode(), b""
            )
        if "--collect-only" in command:
            return subprocess.CompletedProcess(
                command, 0, b"tests/test_chinese.py::test_chinese\n1 item collected\n", b""
            )
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    transitions = runner.RuntimeTransitions()
    for state in list(EvaluatorRuntimeState)[:6]:
        transitions.reach(state, {"prepared": True})
    result = runner._preflight(adapter, "image", source, "preflight", fixture, transitions)
    reached = [item["state"] for item in transitions.evidence()["transitions"]]
    assert reached[-2:] == ["EVALUATOR_IMPORT_VERIFIED", "TEST_COLLECTED"]
    assert result["collection_count"] == 1
    assert result["evaluator_import_verified"] is True
    assert any("PYTHONPATH=/workspace" in command for command in commands)
    assert any("cache_dir=/tmp/pytest-cache" in command for command in commands)
    assert all("runpy.run_path" not in " ".join(command) for command in commands)
