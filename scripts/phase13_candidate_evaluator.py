"""Trusted candidate evaluator composed from the reviewed Phase 12 sandbox."""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from archguard.domain.phase13 import TerminalClassification
from archguard.domain.phase128f import EvaluatorAdapter, Outcome
from scripts import phase128f_runner as qualified
from scripts.phase128f_registry import adapters


def evaluate_candidate(
    task_id: str,
    buggy: Path,
    candidate: Path,
    root: Path,
    repository_root: Path,
    architecture_treatment: bool,
) -> dict[str, Any]:
    root.mkdir(parents=True, mode=0o700)
    try:
        if task_id == "PySnooper-2":
            buggy_attempt, attempt = _evaluate_pysnooper_2(buggy, candidate, root)
        else:
            adapter = next(item for item in adapters() if item.task_id == task_id)
            buggy_attempt, attempt = _evaluate_reviewed(adapter, buggy, candidate, root)
        passed = attempt.outcome is Outcome.PASS
        reproduced = buggy_attempt.outcome is Outcome.EXPECTED_FAILURE
        architecture_status, violations = _architecture(
            candidate, root, repository_root, task_id, architecture_treatment
        )
        architecture_passed = architecture_status in {"passed", "skipped"}
        return {
            "architecture_status": architecture_status,
            "architecture_violations": violations,
            "evaluator_executed": True,
            "buggy_failure_reproduced": reproduced,
            "candidate_test_outcome": "passed" if passed else "failed",
            "tests_fixed": int(passed),
            "regressions": int(not passed),
            "repair_success": reproduced and passed and architecture_passed,
            "classification": (
                TerminalClassification.SUCCESS
                if reproduced and passed and architecture_passed
                else TerminalClassification.REPAIR_FAILURE
            ),
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _evaluate_reviewed(
    adapter: EvaluatorAdapter, buggy: Path, candidate: Path, root: Path
) -> tuple[Any, Any]:
    framework = root / "framework"
    fixed = root / "fixed"
    quarantine = root / "quarantine"
    build = root / "build"
    build.mkdir()
    qualified._acquire_framework(framework)
    qualified._safe_checkout(adapter.repository, adapter.fixed_revision, fixed)
    evaluator = qualified._prepare_evaluator_fixture(adapter, fixed, quarantine)
    qualified._verify_evaluator_identity(adapter, evaluator)
    base, _, _ = qualified._acquire_base_image(adapter, build)
    image, _, _, image_identity = qualified._build_image(adapter, build, base)
    qualified._prepare_project(adapter)
    buggy_identity = {
        "working_directory_fingerprint": qualified._working_tree_fingerprint(buggy),
        "build_context_fingerprint": image_identity["build_context_fingerprint"],
    }
    candidate_identity = {
        "working_directory_fingerprint": qualified._working_tree_fingerprint(candidate),
        "build_context_fingerprint": image_identity["build_context_fingerprint"],
    }
    qualified._preflight(
        adapter, image, buggy, f"phase13-{adapter.task_id.lower()}-buggy-preflight", evaluator
    )
    qualified._preflight(
        adapter,
        image,
        candidate,
        f"phase13-{adapter.task_id.lower()}-candidate-preflight",
        evaluator,
    )
    buggy_attempt = qualified._execute(
        adapter,
        image,
        buggy,
        f"phase13-{adapter.task_id.lower()}-buggy",
        expected_outcome="TEST_FAILURE",
        source_identity=buggy_identity,
        evaluator_fixture=evaluator,
    )
    candidate_attempt = qualified._execute(
        adapter,
        image,
        candidate,
        f"phase13-{adapter.task_id.lower()}-candidate",
        expected_outcome="EXIT_ZERO",
        source_identity=candidate_identity,
        evaluator_fixture=evaluator,
    )
    return buggy_attempt, candidate_attempt


def _evaluate_pysnooper_2(buggy: Path, candidate: Path, root: Path) -> tuple[Any, Any]:
    evaluator = root / "evaluate_custom_repr.py"
    evaluator.write_text(
        "import io\nimport pysnooper\noutput=io.StringIO()\n"
        "@pysnooper.snoop(output,custom_repr=(list,lambda value:'foofoo!'))\n"
        "def exercise():\n values=list(range(10)); return len(values)\n"
        "assert exercise()==10\nassert 'foofoo!' in output.getvalue()\n",
        encoding="utf-8",
    )
    build = root / "pysnooper2-image"
    build.mkdir()
    (build / "Dockerfile").write_text(
        "FROM python:3.8.1\nRUN pip install --no-cache-dir six==1.15.0\nUSER 65532:65532\n",
        encoding="utf-8",
    )
    image = "archguard-phase13-pysnooper2"
    subprocess.run(
        ["docker", "build", "--label", "org.archguard.phase=13", "-t", image, str(build)],
        check=True,
        capture_output=True,
        timeout=1200,
    )

    def run(source: Path, name: str) -> subprocess.CompletedProcess[bytes]:
        command = [
            "docker",
            "run",
            "--name",
            name,
            "--label",
            "org.archguard.phase=13",
            "--platform",
            "linux/amd64",
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=256m",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--pids-limit",
            "128",
            "--memory",
            "536870912",
            "--cpus",
            "1",
            "--user",
            "65532:65532",
            "--env",
            "HOME=/tmp",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            "PYTHONPATH=/source",
            "--volume",
            f"{source}:/source:ro",
            "--volume",
            f"{evaluator}:/evaluator/evaluate.py:ro",
            image,
            "python",
            "/evaluator/evaluate.py",
        ]
        try:
            return subprocess.run(command, capture_output=True, timeout=1200)
        finally:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)

    from archguard.domain.phase128f import AttemptEvidence

    results = (
        (run(buggy, "phase13-pysnooper-2-buggy"), True),
        (run(candidate, "phase13-pysnooper-2-candidate"), False),
    )
    attempts = []
    for result, expect_failure in results:
        outcome = (
            Outcome.EXPECTED_FAILURE
            if expect_failure and result.returncode != 0
            else Outcome.PASS
            if result.returncode == 0
            else Outcome.OTHER_FAILURE
        )
        attempts.append(
            AttemptEvidence(
                outcome,
                result.returncode,
                None
                if result.returncode == 0
                else hashlib.sha256(result.stderr[:65536]).hexdigest(),
                int(result.returncode == 0),
                int(result.returncode != 0),
                0,
                len(result.stdout) + len(result.stderr) > 1048576,
                None if result.returncode == 0 else "ASSERTION_FAILURE",
            )
        )
    return attempts[0], attempts[1]


def _architecture(
    source: Path, root: Path, repository_root: Path, task_id: str, enabled: bool
) -> tuple[str, tuple[tuple[str, int], ...]]:
    if not enabled or task_id == "black-4":
        return "skipped", ()
    snapshot = root / "snapshot.json"
    graph = root / "graph.json"
    profile = root / "profile.json"
    report = root / "report.json"
    commands = (
        ["uv", "run", "archguard", "repository", "analyze", str(source), "--output", str(snapshot)],
        [
            "uv",
            "run",
            "archguard",
            "graph",
            "build",
            "--snapshot",
            str(snapshot),
            "--output",
            str(graph),
        ],
        [
            "uv",
            "run",
            "archguard",
            "architecture",
            "profile",
            "compile",
            str(
                repository_root / "configs/external-profiles/pysnooper-micro-pilot-amended-v2.yaml"
            ),
            "--output",
            str(profile),
        ],
        [
            "uv",
            "run",
            "archguard",
            "architecture",
            "evaluate",
            str(graph),
            "--profile",
            str(profile),
            "--output",
            str(report),
        ],
    )
    for command in commands:
        subprocess.run(command, check=True, capture_output=True, timeout=300)
    import json

    value = json.loads(report.read_text(encoding="utf-8"))
    severities: dict[str, int] = {}
    for violation in value.get("violations", []):
        severity = str(violation.get("severity", "unknown"))
        severities[severity] = severities.get(severity, 0) + 1
    passed = not severities.get("error", 0)
    return ("passed" if passed else "partial"), tuple(sorted(severities.items()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--buggy", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--architecture-treatment", action="store_true")
    arguments = parser.parse_args()
    result = evaluate_candidate(
        arguments.task_id,
        arguments.buggy,
        arguments.candidate,
        arguments.root,
        arguments.repository_root,
        arguments.architecture_treatment,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
