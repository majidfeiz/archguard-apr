import os
from pathlib import Path

import pytest

from archguard.domain.execution import (
    CommandState,
    ExecutionPlan,
    FailurePolicy,
    ResourceLimits,
    ResultAdapter,
    ValidationStage,
)
from archguard.infrastructure.docker_execution import DockerSandbox

pytestmark = pytest.mark.docker


def image() -> str:
    value = os.environ.get("TEST_DOCKER_IMAGE")
    if not value:
        pytest.skip("trusted validation image identity not supplied")
    return value


def test_docker_junit_isolation_and_cleanup(tmp_path: Path) -> None:
    script = (
        "import os,pathlib,socket; assert os.getuid()!=0; "
        "assert not pathlib.Path('/var/run/docker.sock').exists(); "
        "assert 'HOST_SECRET' not in os.environ; "
        "s=socket.socket(); s.settimeout(.2); "
        "blocked=False; "
        "\ntry: s.connect(('1.1.1.1',53))\nexcept OSError: blocked=True\n"
        "assert blocked; "
        "pathlib.Path('junit.xml').write_text('<testsuite><testcase "
        'file="tests/test_fixture.py" name="ok"/></testsuite>\')'
    )
    plan = ExecutionPlan(
        "archguard.execution-plan/v1",
        "docker-smoke",
        image(),
        (
            ValidationStage(
                "smoke",
                ("python", "-c", script),
                ".",
                20,
                ResultAdapter.JUNIT,
                ("junit.xml",),
                FailurePolicy.STOP,
            ),
        ),
        20,
        ResourceLimits(1, 128 * 1024 * 1024, 32, 16 * 1024 * 1024, 4096),
    )
    result = DockerSandbox().execute(plan, tmp_path, {"HOST_SECRET": "must-not-cross"})
    assert result.completed and result.infrastructure_healthy
    assert result.observations[0].state == CommandState.PASSED
    assert result.observations[0].tests[0].test_id == "tests/test_fixture.py::ok"


def test_docker_timeout_removes_container(tmp_path: Path) -> None:
    plan = ExecutionPlan(
        "archguard.execution-plan/v1",
        "docker-timeout",
        image(),
        (
            ValidationStage(
                "timeout",
                ("python", "-c", "import time;time.sleep(10)"),
                ".",
                1,
                ResultAdapter.COMMAND,
            ),
        ),
        1,
        ResourceLimits(1, 128 * 1024 * 1024, 32, 16 * 1024 * 1024, 4096),
    )
    result = DockerSandbox().execute(plan, tmp_path, {})
    assert result.observations[0].state == CommandState.TIMED_OUT
    assert not result.completed


def test_docker_output_is_bounded(tmp_path: Path) -> None:
    plan = ExecutionPlan(
        "archguard.execution-plan/v1",
        "docker-output",
        image(),
        (
            ValidationStage(
                "output",
                ("python", "-c", "print('x'*10000)"),
                ".",
                10,
                ResultAdapter.COMMAND,
            ),
        ),
        10,
        ResourceLimits(1, 128 * 1024 * 1024, 32, 16 * 1024 * 1024, 128),
    )
    result = DockerSandbox().execute(plan, tmp_path, {})
    assert result.observations[0].state == CommandState.PASSED
    assert result.observations[0].stdout_truncated
