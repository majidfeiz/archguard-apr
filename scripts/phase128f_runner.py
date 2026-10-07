#!/usr/bin/env python3
"""GitHub-runner-only sandboxed task qualification; never run by local verification."""

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from archguard.domain.canonical import canonical_json
from archguard.domain.phase128f import (
    BATCH_A,
    BATCH_B,
    AttemptEvidence,
    Classification,
    EvaluatorAdapter,
    Outcome,
    SandboxContract,
    classify,
    prior_evidence_status,
    qualification_decision,
)

MAX_TRANSFER = 2 * 1024**3
MAX_DISK = 8 * 1024**3
ALLOWED_HOSTS = ("github.com", "api.github.com", "pypi.org", "files.pythonhosted.org")
BUGSINPY_REVISION = "11c5f1eea954a42132cfd06bf257766a7963e0fd"


def _run(
    command: list[str], *, cwd: Path | None = None, timeout: int = 1200
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, cwd=cwd, check=True, capture_output=True, timeout=timeout)


def _adapter(value: dict[str, Any]) -> EvaluatorAdapter:
    value = dict(value)
    value["test_selectors"] = tuple(value["test_selectors"])
    value["dependency_constraints"] = tuple(value["dependency_constraints"])
    value["sandbox"] = SandboxContract(**value["sandbox"])
    return EvaluatorAdapter(**value)


def _tasks(selection: str) -> tuple[str, ...]:
    if selection == "batch-a":
        return BATCH_A
    if selection == "batch-b":
        return BATCH_B
    if selection == "all":
        return BATCH_A + BATCH_B
    return (selection,)


def _safe_checkout(repository: str, revision: str, destination: Path) -> None:
    _run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "submodule.recurse=false",
            "-c",
            "filter.lfs.smudge=",
            "-c",
            "filter.lfs.required=false",
            "clone",
            "--quiet",
            "--no-checkout",
            "--filter=blob:none",
            f"{repository}.git",
            str(destination),
        ],
        timeout=600,
    )
    _run(["git", "-C", str(destination), "checkout", "--quiet", "--detach", revision], timeout=600)
    head = _run(["git", "-C", str(destination), "rev-parse", "HEAD"]).stdout.decode().strip()
    if head != revision:
        raise RuntimeError("immutable revision mismatch")
    tree = _run(["git", "-C", str(destination), "ls-tree", "-r", revision]).stdout
    if re.search(rb"^160000 ", tree, re.MULTILINE):
        raise RuntimeError("unsupported gitlink")
    for path in destination.rglob("*"):
        if path.is_symlink() and not path.resolve().is_relative_to(destination.resolve()):
            raise RuntimeError("escaping symlink")
        if path.is_file() and path.stat().st_size < 1024:
            with path.open("rb") as source:
                if source.read(80).startswith(b"version https://git-lfs.github.com/spec/v1"):
                    raise RuntimeError("LFS pointer")


def _acquire_framework(destination: Path) -> None:
    _safe_checkout("https://github.com/soarsmu/BugsInPy", BUGSINPY_REVISION, destination)


def _verify_identities(adapter: EvaluatorAdapter, source: Path, framework: Path) -> None:
    license_path = source / "LICENSE"
    if hashlib.sha256(license_path.read_bytes()).hexdigest() != adapter.source_license_sha256:
        raise RuntimeError("source license identity mismatch")
    relative = adapter.dependency_locator.split(":", 1)[1]
    dependency_path = framework / relative
    if hashlib.sha256(dependency_path.read_bytes()).hexdigest() != adapter.dependency_sha256:
        raise RuntimeError("dependency metadata identity mismatch")


def _build_image(
    adapter: EvaluatorAdapter, build_root: Path
) -> tuple[str, list[dict[str, str]], int]:
    tag = f"archguard-phase128f-{adapter.task_id.lower()}"
    base = f"python:{adapter.python_version}"
    _run(["docker", "image", "inspect", base], timeout=30)
    constraints = " ".join(adapter.dependency_constraints)
    dockerfile = build_root / "Dockerfile"
    dockerfile.write_text(
        "\n".join(
            [
                f"FROM {base}",
                "RUN mkdir -p /wheelhouse && "
                "pip download --no-cache-dir --index-url https://pypi.org/simple/ "
                f"--dest /wheelhouse {constraints} && "
                "sha256sum /wheelhouse/* | sort > /dependency-hashes && "
                "pip install --no-cache-dir /wheelhouse/*",
                "RUN groupadd --gid 65532 evaluator && "
                "useradd --uid 65532 --gid 65532 --no-create-home evaluator",
                "USER 65532:65532",
                "WORKDIR /source",
                "ENV HOME=/tmp PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/source",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _run(
        [
            "docker",
            "build",
            "--network=default",
            "--platform=linux/amd64",
            "--label=archguard.phase=12.8f",
            "--tag",
            tag,
            str(build_root),
        ],
        timeout=1200,
    )
    hashes = _run(["docker", "run", "--rm", "--network", "none", tag, "cat", "/dependency-hashes"])
    packages = []
    for line in hashes.stdout.decode().splitlines():
        digest, filename = line.split(maxsplit=1)
        packages.append({"filename": Path(filename).name, "sha256": digest})
    image_size = int(
        _run(["docker", "image", "inspect", tag, "--format", "{{.Size}}"]).stdout.decode().strip()
    )
    return tag, packages, image_size


def _execute(adapter: EvaluatorAdapter, image: str, source: Path, name: str) -> AttemptEvidence:
    started = time.monotonic()
    command = [adapter.evaluator_entry_point, *adapter.test_selectors]
    preparation = "touch tests/__init__.py && " if adapter.project == "black" else ""
    docker = [
        "docker",
        "run",
        "--name",
        name,
        "--label",
        "archguard.phase=12.8f",
        "--platform",
        "linux/amd64",
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        f"/tmp:rw,noexec,nosuid,size={adapter.sandbox.tmpfs_bytes}",
        "--tmpfs",
        f"/source:rw,nosuid,size={adapter.sandbox.tmpfs_bytes}",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        str(adapter.sandbox.pids),
        "--memory",
        str(adapter.sandbox.memory_bytes),
        "--cpus",
        str(adapter.sandbox.cpus),
        "--user",
        "65532:65532",
        "--volume",
        f"{source}:/input:ro",
        image,
        "sh",
        "-c",
        "cp -a /input/. /source && " + preparation + "exec " + shlex.join(command),
    ]
    try:
        result = subprocess.run(
            docker, capture_output=True, timeout=adapter.sandbox.timeout_seconds
        )
        raw = (result.stdout + result.stderr)[: adapter.sandbox.output_bytes]
        normalized = re.sub(rb"\d+(?:\.\d+)?s", b"<duration>", raw)
        normalized = re.sub(rb"/[^\s:]+", b"<path>", normalized)
        signature = hashlib.sha256(normalized).hexdigest() if result.returncode else None
        outcome = Outcome.PASS if result.returncode == 0 else Outcome.EXPECTED_FAILURE
        text = raw.decode("utf-8", "replace")
        passed = sum(int(value) for value in re.findall(r"(\d+) passed", text))
        failed = sum(int(value) for value in re.findall(r"(\d+) failed", text))
        return AttemptEvidence(
            outcome,
            result.returncode,
            signature,
            passed,
            failed or int(result.returncode != 0),
            min(int((time.monotonic() - started) * 1000), 1_200_000),
            len(result.stdout) + len(result.stderr) > adapter.sandbox.output_bytes,
        )
    except subprocess.TimeoutExpired:
        return AttemptEvidence(Outcome.TIMEOUT, None, None, 0, 0, 1_200_000, True)
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def qualify(adapter: EvaluatorAdapter, root: Path, framework: Path) -> dict[str, Any]:
    task_root = root / adapter.task_id
    buggy = task_root / "buggy"
    fixed = task_root / "fixed"
    build = task_root / "build"
    build.mkdir(parents=True)
    try:
        _safe_checkout(adapter.repository, adapter.buggy_revision, buggy)
        _safe_checkout(adapter.repository, adapter.fixed_revision, fixed)
        _verify_identities(adapter, buggy, framework)
        image, packages, image_size = _build_image(adapter, build)
        attempts = tuple(
            _execute(adapter, image, buggy, f"phase128f-{adapter.task_id.lower()}-buggy-{index}")
            for index in range(1, 4)
        )
        fixed_attempt = _execute(
            adapter, image, fixed, f"phase128f-{adapter.task_id.lower()}-fixed"
        )
        fixed_passed = fixed_attempt.outcome is Outcome.PASS
        classification = classify(attempts, fixed_control_passed=fixed_passed)
    except subprocess.CalledProcessError:
        attempts = tuple(
            AttemptEvidence(Outcome.INFRASTRUCTURE_FAILURE, None, None, 0, 0, 0) for _ in range(3)
        )
        fixed_passed = False
        classification = Classification.INFRASTRUCTURE_FAILURE
        packages = []
        image_size = 0
    prior = prior_evidence_status(adapter.task_id, classification)
    decision = qualification_decision(classification, fixed_passed)
    if prior == "EVIDENCE_CONFLICT_REVIEW_REQUIRED":
        decision = "NOT_QUALIFIED"
    return {
        "adapter_fingerprint": adapter.fingerprint,
        "buggy_attempts": [
            {
                **attempt.__dict__,
                "outcome": attempt.outcome.value,
            }
            for attempt in attempts
        ],
        "buggy_revision": adapter.buggy_revision,
        "classification": classification.value,
        "dependency_artifacts": packages,
        "fixed_control_passed": fixed_passed,
        "fixed_revision": adapter.fixed_revision,
        "prior_evidence_status": prior,
        "qualification_decision": decision,
        "resources": {
            "cpu_limit": adapter.sandbox.cpus,
            "memory_limit_bytes": adapter.sandbox.memory_bytes,
            "output_limit_bytes": adapter.sandbox.output_bytes,
            "pids_limit": adapter.sandbox.pids,
            "timeout_seconds": adapter.sandbox.timeout_seconds,
            "measured_duration_milliseconds": sum(
                attempt.duration_milliseconds for attempt in attempts
            )
            + fixed_attempt.duration_milliseconds
            if "fixed_attempt" in locals()
            else 0,
            "measured_image_bytes": image_size,
            "measured_task_tree_bytes": _tree_bytes(task_root),
        },
        "task_id": adapter.task_id,
    }


def cleanup(root: Path) -> None:
    containers = (
        _run(["docker", "ps", "-aq", "--filter", "label=archguard.phase=12.8f"], timeout=30)
        .stdout.decode()
        .split()
    )
    if containers:
        subprocess.run(["docker", "rm", "-f", *containers], check=False, capture_output=True)
    images = (
        _run(["docker", "images", "-q", "--filter", "label=archguard.phase=12.8f"], timeout=30)
        .stdout.decode()
        .split()
    )
    if images:
        subprocess.run(["docker", "image", "rm", "-f", *images], check=False, capture_output=True)
    shutil.rmtree(root, ignore_errors=True)


def _tree_bytes(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapters", type=Path, required=True)
    parser.add_argument("--selection", required=True)
    parser.add_argument("--external-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.uname().sysname != "Linux" or os.uname().machine != "x86_64":
        raise SystemExit("native Linux x86_64 required")
    registry = json.loads(args.adapters.read_text(encoding="utf-8"))
    adapters = {_adapter(value).task_id: _adapter(value) for value in registry["adapters"]}
    tasks = _tasks(args.selection)
    if not set(tasks) <= set(adapters):
        raise SystemExit("selection is not an adapter-backed selected task")
    args.external_root.mkdir(parents=True, exist_ok=False)
    results: list[dict[str, Any]] = []
    try:
        framework = args.external_root / "framework-metadata"
        _acquire_framework(framework)
        for task in tasks:
            results.append(qualify(adapters[task], args.external_root, framework))
            if (
                sum(
                    result["classification"] == Classification.INFRASTRUCTURE_FAILURE
                    for result in results
                )
                > 1
            ):
                break
            if _tree_bytes(args.external_root) > MAX_DISK:
                raise RuntimeError("temporary disk ceiling exceeded")
        args.output.write_bytes(canonical_json(results))
    finally:
        cleanup(args.external_root)


if __name__ == "__main__":
    main()
