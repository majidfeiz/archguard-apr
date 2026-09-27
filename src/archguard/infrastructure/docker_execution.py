"""Fail-closed Docker CLI sandbox; candidate code is never executed on the host."""

import hashlib
import os
import secrets
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import BinaryIO

from archguard.domain.canonical import canonical_json
from archguard.domain.execution import (
    CommandObservation,
    CommandState,
    ExecutionEvidence,
    ExecutionPlan,
    ResultAdapter,
    TestCaseObservation,
)
from archguard.infrastructure.junit import parse_junit


class DockerInfrastructureError(RuntimeError):
    """Docker is unavailable or could not enforce the requested sandbox."""


@dataclass
class _Capture:
    data: bytearray
    truncated: bool = False


def _drain(stream: BinaryIO, capture: _Capture, limit: int) -> None:
    while chunk := stream.read(65536):
        remaining = max(0, limit - len(capture.data))
        capture.data.extend(chunk[:remaining])
        capture.truncated |= len(chunk) > remaining


class DockerSandbox:
    def __init__(self, executable: str = "docker") -> None:
        self.executable = executable

    @staticmethod
    def _copy_workspace(source: Path, destination: Path) -> None:
        root = source.resolve(strict=True)
        if not root.is_dir() or source.is_symlink():
            raise ValueError("workspace must be a real directory")
        shutil.copytree(root, destination, symlinks=True)
        destination.chmod(0o777)
        for item in destination.rglob("*"):
            if item.is_symlink():
                try:
                    item.resolve(strict=True).relative_to(destination.resolve())
                except (OSError, ValueError):
                    raise ValueError("workspace contains a symlink escape") from None
            elif item.is_dir():
                item.chmod(item.stat().st_mode | 0o777)
            elif item.is_file():
                item.chmod(item.stat().st_mode | 0o666)

    def _docker_argv(
        self,
        plan: ExecutionPlan,
        workspace: Path,
        stage_index: int,
        environment: Mapping[str, str],
        name: str,
    ) -> list[str]:
        stage = plan.stages[stage_index]
        limits = plan.limits
        argv = [
            self.executable,
            "run",
            "--name",
            name,
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--user",
            "10001:10001",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory",
            str(limits.memory_bytes),
            "--cpus",
            str(limits.cpu_count),
            "--pids-limit",
            str(limits.pid_limit),
            "--ulimit",
            f"fsize={limits.temporary_storage_bytes}:{limits.temporary_storage_bytes}",
            "--tmpfs",
            f"/tmp:rw,noexec,nosuid,nodev,size={limits.temporary_storage_bytes}",
            "--mount",
            f"type=bind,src={workspace.resolve(strict=True)},dst=/workspace",
            "--workdir",
            f"/workspace/{stage.working_directory}",
            "--entrypoint",
            stage.argv[0],
        ]
        constants = dict(plan.environment)
        for key in sorted(constants):
            argv.extend(("--env", f"{key}={constants[key]}"))
        for key in sorted(plan.allowed_environment):
            if key in environment:
                argv.extend(("--env", f"{key}={environment[key]}"))
        return [*argv, plan.image, *stage.argv[1:]]

    def _remove(self, name: str) -> None:
        try:
            subprocess.run(
                [self.executable, "rm", "--force", name],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=False,
                env={"PATH": os.environ.get("PATH", "")},
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

    def execute(
        self, plan: ExecutionPlan, workspace: Path, allowed_environment: Mapping[str, str]
    ) -> ExecutionEvidence:
        observations: list[CommandObservation] = []
        healthy, completed = True, True
        started = monotonic()
        with tempfile.TemporaryDirectory(prefix="archguard-sandbox-") as parent:
            copied = Path(parent) / "workspace"
            self._copy_workspace(workspace, copied)
            for index, stage in enumerate(plan.stages):
                name = "archguard-p7-" + secrets.token_hex(16)
                argv = self._docker_argv(plan, copied, index, allowed_environment, name)
                out, err = _Capture(bytearray()), _Capture(bytearray())
                exit_code: int | None = None
                state, diagnostic = CommandState.INFRASTRUCTURE_ERROR, None
                try:
                    process = subprocess.Popen(
                        argv,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env={"PATH": os.environ.get("PATH", "")},
                        start_new_session=True,
                    )
                    assert process.stdout is not None and process.stderr is not None
                    threads = [
                        threading.Thread(
                            target=_drain,
                            args=(process.stdout, out, plan.limits.maximum_output_bytes),
                            daemon=True,
                        ),
                        threading.Thread(
                            target=_drain,
                            args=(process.stderr, err, plan.limits.maximum_output_bytes),
                            daemon=True,
                        ),
                    ]
                    for thread in threads:
                        thread.start()
                    remaining = min(
                        stage.timeout_seconds,
                        max(0.001, plan.total_timeout_seconds - (monotonic() - started)),
                    )
                    try:
                        exit_code = process.wait(timeout=remaining)
                        if exit_code == 125:
                            state = CommandState.INFRASTRUCTURE_ERROR
                            healthy, completed = False, False
                            diagnostic = "container_start_failed"
                        else:
                            state = CommandState.PASSED if exit_code == 0 else CommandState.FAILED
                    except subprocess.TimeoutExpired:
                        state, completed = CommandState.TIMED_OUT, False
                        self._remove(name)
                        process.kill()
                        process.wait(timeout=5)
                    except KeyboardInterrupt:
                        state, completed = CommandState.CANCELLED, False
                        self._remove(name)
                        process.kill()
                        process.wait(timeout=5)
                    for thread in threads:
                        thread.join(timeout=5)
                except (OSError, subprocess.SubprocessError):
                    healthy, completed = False, False
                    diagnostic = "docker_unavailable_or_start_failed"
                finally:
                    self._remove(name)
                present: list[str] = []
                missing: list[str] = []
                tests: tuple[TestCaseObservation, ...] = ()
                for artifact in stage.expected_artifacts:
                    target = (copied / artifact).resolve()
                    try:
                        target.relative_to(copied.resolve())
                        valid = target.is_file() and not target.is_symlink()
                    except (OSError, ValueError):
                        valid = False
                    (present if valid else missing).append(artifact)
                if missing and state == CommandState.PASSED:
                    state, completed = CommandState.INVALID_RESULT, False
                    diagnostic = "required_artifact_missing"
                if stage.adapter == ResultAdapter.JUNIT and not missing:
                    try:
                        tests = parse_junit(copied / stage.expected_artifacts[0])
                    except (ValueError, OSError, IndexError):
                        state, completed = CommandState.INVALID_RESULT, False
                        diagnostic = "junit_invalid"
                command_sha = hashlib.sha256(canonical_json(list(stage.argv))).hexdigest()
                observations.append(
                    CommandObservation(
                        stage.stage_id,
                        index,
                        command_sha,
                        state,
                        exit_code,
                        hashlib.sha256(out.data).hexdigest(),
                        hashlib.sha256(err.data).hexdigest(),
                        out.truncated,
                        err.truncated,
                        tuple(present),
                        tuple(missing),
                        tests,
                        diagnostic,
                    )
                )
                if state != CommandState.PASSED and stage.failure_policy.value == "stop":
                    break
        return ExecutionEvidence(
            "archguard.execution-evidence/v1",
            plan.plan_id,
            plan.plan_fingerprint,
            tuple(observations),
            completed,
            healthy,
        )
