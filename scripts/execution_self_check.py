"""Controlled Phase 7 engineering check; produces no repository artifacts."""

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from archguard.domain.execution import (
    DeltaState,
    ExecutionPlan,
    FailurePolicy,
    ResourceLimits,
    ResultAdapter,
    ValidationStage,
    compare_evidence,
)
from archguard.infrastructure.docker_execution import DockerSandbox
from archguard.infrastructure.execution_artifacts import LocalExecutionArtifacts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    script = (
        "import pathlib; fixed=pathlib.Path('fixed').exists(); "
        "state='' if fixed else '<failure/>'; "
        "pathlib.Path('junit.xml').write_text("
        'f\'<testsuite><testcase file="tests/test_fixture.py" name="target">{state}\''
        "+'</testcase></testsuite>')"
    )
    plan = ExecutionPlan(
        "archguard.execution-plan/v1",
        "phase7-self-check",
        args.image,
        (
            ValidationStage(
                "tests",
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
        target_tests=("tests/test_fixture.py::target",),
        allow_persistent_failures=False,
    )
    sandbox = DockerSandbox()
    with (
        tempfile.TemporaryDirectory(prefix="archguard-self-baseline-") as baseline_dir,
        tempfile.TemporaryDirectory(prefix="archguard-self-candidate-") as candidate_dir,
    ):
        Path(candidate_dir, "fixed").touch()
        baseline = sandbox.execute(plan, Path(baseline_dir), {})
        candidate = sandbox.execute(plan, Path(candidate_dir), {})
        candidate_repeat = sandbox.execute(plan, Path(candidate_dir), {})
    delta = compare_evidence(baseline, candidate, plan)
    artifacts = LocalExecutionArtifacts()
    values = {
        "baseline": baseline,
        "candidate": candidate,
        "candidate-repeat": candidate_repeat,
        "delta": delta,
    }
    hashes: dict[str, str] = {}
    sizes: dict[str, int] = {}
    for name, value in values.items():
        target = args.output / f"{name}.json"
        artifacts.write(value, target)
        raw = target.read_bytes()
        hashes[name] = hashlib.sha256(raw).hexdigest()
        sizes[name] = len(raw)
    summary = {
        "accepted": delta.accepted,
        "fixed": sum(item.state == DeltaState.FIXED for item in delta.transitions),
        "regressed": sum(item.state == DeltaState.REGRESSED for item in delta.transitions),
        "candidate_repeated_byte_identical": hashes["candidate"] == hashes["candidate-repeat"],
        "artifact_sha256": hashes,
        "artifact_bytes": sizes,
    }
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
