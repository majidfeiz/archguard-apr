from dataclasses import replace
from pathlib import Path

import pytest

from archguard.application.services.execution import CompareFunctionalBehavior
from archguard.domain.execution import (
    EXECUTION_EVIDENCE_SCHEMA,
    EXECUTION_PLAN_SCHEMA,
    CommandObservation,
    CommandState,
    DeltaState,
    ExecutionEvidence,
    ExecutionPlan,
    FailurePolicy,
    ResourceLimits,
    ResultAdapter,
    ValidationStage,
    compare_evidence,
)
from archguard.domain.execution import (
    TestCaseObservation as CaseObservation,
)
from archguard.domain.execution import (
    TestState as CaseState,
)
from archguard.infrastructure.docker_execution import DockerSandbox
from archguard.infrastructure.execution_artifacts import LocalExecutionArtifacts
from archguard.infrastructure.execution_plans import LocalExecutionPlans, canonical_plan
from archguard.infrastructure.junit import parse_junit


def limits() -> ResourceLimits:
    return ResourceLimits(1.0, 64 * 1024 * 1024, 64, 16 * 1024 * 1024, 4096)


def stage(**changes: object) -> ValidationStage:
    values = dict(
        stage_id="tests",
        argv=("python", "-m", "pytest"),
        working_directory=".",
        timeout_seconds=30,
        adapter=ResultAdapter.COMMAND,
        expected_artifacts=(),
        failure_policy=FailurePolicy.STOP,
    )
    values.update(changes)
    return ValidationStage(**values)  # type: ignore[arg-type]


def plan(**changes: object) -> ExecutionPlan:
    values = dict(
        schema=EXECUTION_PLAN_SCHEMA,
        plan_id="fixture",
        image="python@sha256:" + "1" * 64,
        stages=(stage(),),
        total_timeout_seconds=60,
        limits=limits(),
        allowed_environment=("CI",),
        environment=(("PYTHONDONTWRITEBYTECODE", "1"),),
    )
    values.update(changes)
    return ExecutionPlan(**values)  # type: ignore[arg-type]


def observation(
    state: CommandState = CommandState.PASSED,
    tests: tuple[CaseObservation, ...] = (),
) -> CommandObservation:
    return CommandObservation(
        "tests",
        0,
        "2" * 64,
        state,
        0,
        "3" * 64,
        "4" * 64,
        False,
        False,
        (),
        (),
        tests,
    )


def evidence(
    *tests: CaseObservation, healthy: bool = True, completed: bool = True
) -> ExecutionEvidence:
    return ExecutionEvidence(
        EXECUTION_EVIDENCE_SCHEMA,
        "fixture",
        "1" * 64,
        (observation(tests=tuple(tests)),),
        completed,
        healthy,
    )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"schema": "bad"}, "schema"),
        ({"image": "python:latest"}, "pinned"),
        ({"stages": ()}, "stages"),
        ({"stages": (stage(), stage())}, "duplicate"),
        ({"total_timeout_seconds": 0}, "timeout"),
        ({"total_timeout_seconds": 10}, "exceed"),
        ({"allowed_environment": ("HOME-path",)}, "environment"),
        ({"allowed_environment": ("CI", "CI")}, "duplicate"),
        ({"environment": (("CI", "yes"),)}, "conflict"),
    ],
)
def test_plan_rejects_invalid(change: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        plan(**change)


@pytest.mark.parametrize(
    "change",
    [
        {"argv": ()},
        {"argv": ("",)},
        {"argv": ("x\x00",)},
        {"working_directory": "/tmp"},
        {"working_directory": "../x"},
        {"timeout_seconds": 0},
        {"expected_artifacts": ("../x",)},
    ],
)
def test_stage_rejects_unsafe_values(change: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        stage(**change)


@pytest.mark.parametrize(
    "value",
    [
        (0, 64 * 1024 * 1024, 64, 16 * 1024 * 1024, 10),
        (1, 1, 64, 16 * 1024 * 1024, 10),
        (1, 64 * 1024 * 1024, 0, 16 * 1024 * 1024, 10),
        (1, 64 * 1024 * 1024, 64, 0, 10),
        (1, 64 * 1024 * 1024, 64, 16 * 1024 * 1024, 0),
    ],
)
def test_resource_limits_are_bounded(value: tuple[float, int, int, int, int]) -> None:
    with pytest.raises(ValueError):
        ResourceLimits(*value)


def test_plan_fingerprint_is_stable_and_checked() -> None:
    first = plan()
    assert first == plan()
    assert first.plan_fingerprint == plan().plan_fingerprint
    with pytest.raises(ValueError, match="fingerprint"):
        replace(first, plan_fingerprint="0" * 64)


def test_all_functional_transitions_and_policy() -> None:
    baseline = evidence(
        CaseObservation("fixed", CaseState.FAILED),
        CaseObservation("regressed", CaseState.PASSED),
        CaseObservation("persistent", CaseState.ERROR),
        CaseObservation("passed", CaseState.PASSED),
        CaseObservation("removed", CaseState.SKIPPED),
        CaseObservation("changed", CaseState.SKIPPED),
    )
    candidate = evidence(
        CaseObservation("fixed", CaseState.PASSED),
        CaseObservation("regressed", CaseState.FAILED),
        CaseObservation("persistent", CaseState.FAILED),
        CaseObservation("passed", CaseState.XPASS),
        CaseObservation("added", CaseState.PASSED),
        CaseObservation("changed", CaseState.PASSED),
    )
    delta = compare_evidence(baseline, candidate, plan(target_tests=("fixed",)))
    by_id = {item.test_id: item.state for item in delta.transitions}
    assert by_id == {
        "added": DeltaState.CANDIDATE_ONLY,
        "changed": DeltaState.STATUS_CHANGED,
        "fixed": DeltaState.FIXED,
        "passed": DeltaState.PASSED_BOTH,
        "persistent": DeltaState.PERSISTENT_FAILURE,
        "regressed": DeltaState.REGRESSED,
        "removed": DeltaState.BASELINE_ONLY,
    }
    assert not delta.accepted
    assert set(delta.rejection_reasons) == {
        "baseline_test_missing",
        "persistent_failure",
        "regression",
    }


def test_policy_rejects_health_completion_and_unfixed_target() -> None:
    delta = compare_evidence(
        evidence(healthy=False), evidence(completed=False), plan(target_tests=("missing",))
    )
    assert set(delta.rejection_reasons) == {
        "execution_incomplete",
        "infrastructure_unhealthy",
        "target_not_fixed",
    }


def test_junit_parses_states_and_normalizes_paths(tmp_path: Path) -> None:
    report = tmp_path / "junit.xml"
    report.write_text("""<testsuite><testcase file="tests/test_a.py" name="ok"/>
      <testcase classname="suite" name="bad"><failure/></testcase>
      <testcase classname="suite" name="boom"><error/></testcase>
      <testcase classname="suite" name="skip"><skipped/></testcase>
      <testcase classname="suite" name="expected"><skipped type="pytest.xfail"/></testcase>
      <testcase classname="suite" name="surprise" status="xpass"/></testsuite>""")
    assert [item.state for item in parse_junit(report)] == [
        CaseState.FAILED,
        CaseState.ERROR,
        CaseState.XFAIL,
        CaseState.SKIPPED,
        CaseState.XPASS,
        CaseState.PASSED,
    ]


@pytest.mark.parametrize(
    "xml", ["<bad", "<testsuite><testcase name='x'/><testcase name='x'/></testsuite>"]
)
def test_junit_rejects_malformed_or_duplicate(tmp_path: Path, xml: str) -> None:
    report = tmp_path / "junit.xml"
    report.write_text(xml)
    with pytest.raises(ValueError):
        parse_junit(report)


def test_plan_and_evidence_artifacts_are_canonical_and_immutable(tmp_path: Path) -> None:
    value = plan()
    path = tmp_path / "plan.json"
    LocalExecutionPlans().write(value, path)
    assert path.read_bytes() == canonical_plan(value)
    assert LocalExecutionPlans().load(path) == value
    evidence_path = tmp_path / "evidence.json"
    artifacts = LocalExecutionArtifacts()
    artifacts.write(evidence(), evidence_path)
    assert artifacts.read(evidence_path, ExecutionEvidence) == evidence()
    with pytest.raises(FileExistsError):
        artifacts.write(evidence(), evidence_path)


def test_yaml_plan_loads(tmp_path: Path) -> None:
    path = tmp_path / "plan.yaml"
    path.write_text(canonical_plan(plan()).decode())
    assert LocalExecutionPlans().load(path).plan_id == "fixture"


def test_docker_argv_has_mandatory_isolation_controls(tmp_path: Path) -> None:
    argv = DockerSandbox()._docker_argv(plan(), tmp_path, 0, {"CI": "true", "SECRET": "no"}, "safe")
    rendered = " ".join(argv)
    for option in (
        "--network none",
        "--read-only",
        "--user 10001:10001",
        "--cap-drop ALL",
        "no-new-privileges",
        "--pids-limit",
        "--tmpfs",
        "--entrypoint python",
    ):
        assert option in rendered
    assert "SECRET" not in rendered
    assert "/var/run/docker.sock" not in rendered


def test_docker_unavailable_is_structured_failure(tmp_path: Path) -> None:
    (tmp_path / "file").write_text("data")
    result = DockerSandbox("definitely-not-a-docker-binary").execute(plan(), tmp_path, {})
    assert not result.infrastructure_healthy
    assert not result.completed
    assert result.observations[0].state == CommandState.INFRASTRUCTURE_ERROR


def test_comparison_service_uses_separate_equivalent_workspaces(tmp_path: Path) -> None:
    class Context:
        def __init__(self, path: Path) -> None:
            self.path = path

        def __enter__(self) -> Path:
            self.path.mkdir()
            return self.path

        def __exit__(self, *args: object) -> None:
            pass

    class Workspaces:
        count = 0

        def workspace(self, repository: Path, baseline_commit: str) -> Context:
            self.count += 1
            return Context(tmp_path / f"workspace-{self.count}")

        def check_apply(self, workspace: Path, raw: bytes) -> bool:
            return raw == b"patch"

        def apply(self, workspace: Path, raw: bytes) -> bool:
            (workspace / "patched").touch()
            return True

    class Sandbox:
        def execute(
            self, value: ExecutionPlan, workspace: Path, allowed_environment: dict[str, str]
        ) -> ExecutionEvidence:
            state = CaseState.PASSED if (workspace / "patched").exists() else CaseState.FAILED
            return evidence(CaseObservation("target", state))

    workspaces = Workspaces()
    before, after, delta = CompareFunctionalBehavior(workspaces, Sandbox()).execute(  # type: ignore[arg-type]
        tmp_path, "a" * 40, b"patch", plan(target_tests=("target",)), {}
    )
    assert before != after
    assert delta.accepted
    assert delta.transitions[0].state == DeltaState.FIXED
    assert workspaces.count == 2
