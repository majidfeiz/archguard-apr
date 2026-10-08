#!/usr/bin/env python3
"""GitHub-runner-only sandboxed task qualification; never run by local verification."""

import argparse
import hashlib
import json
import os
import re
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
    EvaluatorValidationStatus,
    FixedControlStage,
    Outcome,
    SandboxContract,
    classify,
    prior_evidence_status,
    qualification_decision,
)

MAX_TRANSFER = 2 * 1024**3
MAX_DISK = 8 * 1024**3
ALLOWED_HOSTS = (
    "github.com",
    "api.github.com",
    "registry-1.docker.io",
    "auth.docker.io",
    "production.cloudflare.docker.com",
    "pypi.org",
    "files.pythonhosted.org",
)
BUGSINPY_REVISION = "11c5f1eea954a42132cfd06bf257766a7963e0fd"
OWNED_BASE_REFERENCES: set[str] = set()


def _run(
    command: list[str], *, cwd: Path | None = None, timeout: int = 1200
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, cwd=cwd, check=True, capture_output=True, timeout=timeout)


def _adapter(value: dict[str, Any]) -> EvaluatorAdapter:
    value = dict(value)
    value["test_selectors"] = tuple(value["test_selectors"])
    value["dependency_constraints"] = tuple(value["dependency_constraints"])
    value["evaluator_argv"] = tuple(value["evaluator_argv"])
    value["buggy_test_selectors"] = tuple(value.get("buggy_test_selectors", ()))
    value["fixed_test_selectors"] = tuple(value.get("fixed_test_selectors", ()))
    value["installation_plan"] = tuple(value.get("installation_plan", ()))
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


def _safe_checkout(repository: str, revision: str, destination: Path) -> dict[str, Any]:
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
    acquired_revision = (
        _run(["git", "-C", str(destination), "rev-parse", revision]).stdout.decode().strip()
    )
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
    tree_identity = (
        _run(["git", "-C", str(destination), "rev-parse", "HEAD^{tree}"]).stdout.decode().strip()
    )
    return {
        "acquired_repository_revision": acquired_revision,
        "build_context_fingerprint": None,
        "checked_out_head": head,
        "container_visible_source_fingerprint": None,
        "git_tree_identity": tree_identity,
        "requested_revision": revision,
        "working_directory_fingerprint": _working_tree_fingerprint(destination),
    }


def _working_tree_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if not relative.parts or relative.parts[0] == ".git":
            continue
        mode = path.lstat().st_mode & 0o777
        if path.is_symlink():
            kind = b"L"
            content = os.readlink(path).encode("utf-8", "surrogateescape")
        elif path.is_file():
            kind = b"F"
            content = path.read_bytes()
        else:
            continue
        digest.update(relative.as_posix().encode("utf-8", "surrogateescape"))
        digest.update(b"\0" + kind + f"{mode:o}".encode() + b"\0")
        digest.update(hashlib.sha256(content).digest())
    return digest.hexdigest()


def _acquire_framework(destination: Path) -> None:
    _safe_checkout("https://github.com/soarsmu/BugsInPy", BUGSINPY_REVISION, destination)


def _verify_identities(adapter: EvaluatorAdapter, source: Path, framework: Path) -> None:
    license_path = source / "LICENSE"
    if hashlib.sha256(license_path.read_bytes()).hexdigest() != adapter.source_license_sha256:
        raise RuntimeError("source license identity mismatch")
    relative = adapter.dependency_locator.split(":", 1)[1]
    dependency_path = framework / relative
    if (
        hashlib.sha256(dependency_path.read_bytes()).hexdigest()
        != adapter.upstream_requirements_sha256
    ):
        raise RuntimeError("dependency metadata identity mismatch")


def _acquire_base_image(
    adapter: EvaluatorAdapter, build_root: Path
) -> tuple[str, dict[str, Any], int]:
    reference = f"python:{adapter.python_version}"
    existed = (
        subprocess.run(
            ["docker", "image", "inspect", reference], capture_output=True, check=False
        ).returncode
        == 0
    )
    _run(["docker", "pull", "--platform", "linux/amd64", reference], timeout=1200)
    if not existed:
        OWNED_BASE_REFERENCES.add(reference)
        (build_root / "owned-base-reference.txt").write_text(reference + "\n", encoding="ascii")
    details = json.loads(_run(["docker", "image", "inspect", reference]).stdout)[0]
    if details.get("Architecture") != "amd64" or details.get("Os") != "linux":
        raise RuntimeError("base image platform identity mismatch")
    tags = details.get("RepoTags") or []
    if reference not in tags:
        raise RuntimeError("base image repository/tag identity mismatch")
    identity = {
        "architecture": details["Architecture"],
        "declared_reference": reference,
        "image_id": details["Id"],
        "operating_system": details["Os"],
        "repository_digests": sorted(details.get("RepoDigests") or []),
        "repository_tags": sorted(tags),
    }
    owned_reference = f"archguard-phase128f-base-{adapter.python_version}"
    base_dockerfile = build_root / "BaseDockerfile"
    base_dockerfile.write_text(f"FROM {reference}\n", encoding="utf-8")
    _run(
        [
            "docker",
            "build",
            "--pull=false",
            "--platform=linux/amd64",
            "--label=archguard.phase=12.8f",
            "--file",
            str(base_dockerfile),
            "--tag",
            owned_reference,
            str(build_root),
        ],
        timeout=600,
    )
    return owned_reference, identity, int(details.get("Size", 0))


def _build_image(
    adapter: EvaluatorAdapter, build_root: Path, base: str
) -> tuple[str, list[dict[str, str]], int, dict[str, str]]:
    tag = f"archguard-phase128f-{adapter.task_id.lower()}"
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
                "WORKDIR /workspace",
                "ENV HOME=/tmp PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/workspace",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _run(
        [
            "docker",
            "build",
            "--pull=false",
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
    image_id = (
        _run(["docker", "image", "inspect", tag, "--format", "{{.Id}}"]).stdout.decode().strip()
    )
    return (
        tag,
        packages,
        image_size,
        {
            "build_context_fingerprint": hashlib.sha256(dockerfile.read_bytes()).hexdigest(),
            "image_id": image_id,
            "source_in_image": "ABSENT_DEPENDENCY_ONLY",
            "tag": tag,
        },
    )


def _sha256_record(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _fixed_control_record(
    adapter: EvaluatorAdapter,
    attempt: AttemptEvidence,
    dependency_environment_fingerprint: str,
    image_identity: dict[str, str],
    source_identity: dict[str, Any],
) -> dict[str, Any]:
    if attempt.outcome is Outcome.EXPECTED_FAILURE:
        raise RuntimeError("fixed control cannot have EXPECTED_FAILURE outcome")
    stage = (
        FixedControlStage.TEST_COLLECTION
        if attempt.normalized_failure_class
        in {"IMPORT_ERROR", "COLLECTION_ERROR", "SELECTOR_NOT_FOUND"}
        else FixedControlStage.TEST_EXECUTION
    )
    infrastructure = attempt.outcome in {
        Outcome.INFRASTRUCTURE_FAILURE,
        Outcome.RESOURCE_LIMIT,
        Outcome.TIMEOUT,
    }
    failure_signature = attempt.failure_signature
    if failure_signature is None and attempt.normalized_failure_class is not None:
        failure_signature = _sha256_record(
            {"normalized_failure_class": attempt.normalized_failure_class}
        )
    diagnostic = (
        {
            "command_category": "FIXED_CONTROL_EXECUTION",
            "failure_code": f"FIXED_CONTROL_{attempt.outcome.value}",
            "failure_stage": "FIXED_CONTROL_EXECUTION",
            "normalized_error_class": attempt.normalized_failure_class,
            "normalized_stderr_sha256": failure_signature,
            "process_return_code": attempt.exit_code,
            "retryable": attempt.outcome is Outcome.TIMEOUT,
        }
        if infrastructure
        else None
    )
    return {
        "attempted": True,
        "collection_count": (
            0
            if attempt.normalized_failure_class
            in {"IMPORT_ERROR", "COLLECTION_ERROR", "SELECTOR_NOT_FOUND"}
            else attempt.tests_passed + attempt.tests_failed
        ),
        "dependency_environment_fingerprint": dependency_environment_fingerprint,
        "duration_milliseconds": attempt.duration_milliseconds,
        "evaluator_selector_fingerprint": _sha256_record(
            {"argv": list(adapter.evaluator_argv), "selectors": list(adapter.test_selectors)}
        ),
        "expected_outcome": "EXIT_ZERO",
        "expected_test_framework": adapter.evaluator_argv[2],
        "exit_code": attempt.exit_code,
        "failure_signature_sha256": failure_signature,
        "image_identity": image_identity,
        "infrastructure_diagnostic": diagnostic,
        "normalized_failure_class": attempt.normalized_failure_class,
        "outcome": attempt.outcome.value,
        "output_truncated": attempt.output_truncated,
        "revision": adapter.fixed_revision,
        "project_installation_mode": "DEPENDENCIES_ONLY_NO_TARGET_INSTALL",
        "selected_test_fingerprint": _sha256_record(
            {
                "selectors": list(adapter.test_selectors),
                "tree": source_identity["git_tree_identity"],
            }
        ),
        "source_identity": source_identity,
        "stage": stage.value,
        "tests_failed": attempt.tests_failed,
        "tests_passed": attempt.tests_passed,
    }


def _prepare_project(adapter: EvaluatorAdapter) -> None:
    """Explicit reviewed installation stage; v2 adapters declare no install mutation."""
    if not adapter.evaluator_argv:
        raise RuntimeError("adapter has no reviewed evaluator")


def _prepare_evaluator_fixture(adapter: EvaluatorAdapter, fixed: Path, quarantine: Path) -> Path:
    if adapter.evaluator_source_type != "FIXED_REVISION_QUARANTINED_TEST":
        raise RuntimeError("reviewed external evaluator required")
    assert adapter.evaluator_fixture_path is not None
    source = fixed / adapter.evaluator_fixture_path
    destination = quarantine / adapter.evaluator_fixture_path
    destination.parent.mkdir(parents=True)
    shutil.copyfile(source, destination)
    if hashlib.sha256(destination.read_bytes()).hexdigest() != adapter.evaluator_fixture_sha256:
        raise RuntimeError("external evaluator identity mismatch")
    return destination


def _fixed_control_not_executed(
    adapter: EvaluatorAdapter,
    failure_stage: str,
    diagnostic: dict[str, Any],
    dependency_environment_fingerprint: str | None,
    image_identity: dict[str, str] | None,
    source_identity: dict[str, Any] | None,
) -> dict[str, Any]:
    stages = {
        "SOURCE_ACQUISITION": FixedControlStage.ACQUISITION,
        "IDENTITY_VERIFICATION": FixedControlStage.REVISION_VALIDATION,
        "BASE_IMAGE_ACQUISITION": FixedControlStage.IMAGE_BUILD,
        "DEPENDENCY_BUILD": FixedControlStage.DEPENDENCY_RESOLUTION,
        "PROJECT_INSTALL": FixedControlStage.PROJECT_INSTALL,
        "BUGGY_EXECUTION": FixedControlStage.TEST_EXECUTION,
        "FIXED_CONTROL_EXECUTION": FixedControlStage.TEST_EXECUTION,
    }
    attempted = failure_stage == "FIXED_CONTROL_EXECUTION"
    return {
        "attempted": attempted,
        "collection_count": 0,
        "dependency_environment_fingerprint": dependency_environment_fingerprint,
        "duration_milliseconds": 0,
        "evaluator_selector_fingerprint": _sha256_record(
            {"argv": list(adapter.evaluator_argv), "selectors": list(adapter.test_selectors)}
        ),
        "expected_outcome": "EXIT_ZERO",
        "expected_test_framework": adapter.evaluator_argv[2],
        "exit_code": diagnostic["process_return_code"] if attempted else None,
        "failure_signature_sha256": diagnostic["normalized_stderr_sha256"],
        "image_identity": image_identity,
        "infrastructure_diagnostic": diagnostic,
        "normalized_failure_class": diagnostic["failure_code"],
        "outcome": Outcome.INFRASTRUCTURE_FAILURE.value,
        "output_truncated": False,
        "revision": adapter.fixed_revision,
        "project_installation_mode": "DEPENDENCIES_ONLY_NO_TARGET_INSTALL",
        "selected_test_fingerprint": None,
        "source_identity": source_identity,
        "stage": stages[failure_stage].value,
        "tests_failed": 0,
        "tests_passed": 0,
    }


def _container_source_fingerprint(
    adapter: EvaluatorAdapter, image: str, source: Path, name: str
) -> str:
    script = """import hashlib,os,pathlib,stat,sys
root=pathlib.Path(sys.argv[1]); digest=hashlib.sha256()
for path in sorted(root.rglob('*')):
 rel=path.relative_to(root)
 if not rel.parts or rel.parts[0]=='.git': continue
 mode=path.lstat().st_mode & 0o777
 if path.is_symlink(): kind=b'L'; content=os.readlink(path).encode('utf-8','surrogateescape')
 elif path.is_file(): kind=b'F'; content=path.read_bytes()
 else: continue
 digest.update(rel.as_posix().encode('utf-8','surrogateescape'))
 digest.update(b'\\0'+kind+f'{mode:o}'.encode()+b'\\0')
 digest.update(hashlib.sha256(content).digest())
print(digest.hexdigest())
"""
    command = [
        "docker",
        "run",
        "--rm",
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
        f"{source}:/workspace:ro",
        "--workdir",
        "/workspace",
        image,
        "python",
        "-c",
        script,
        "/workspace",
    ]
    result = subprocess.run(command, capture_output=True, timeout=120)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, command, output=result.stdout, stderr=result.stderr
        )
    value = result.stdout.decode("ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise RuntimeError("invalid container-visible source fingerprint")
    return value


def _execute(
    adapter: EvaluatorAdapter,
    image: str,
    source: Path,
    name: str,
    *,
    expected_outcome: str,
    source_identity: dict[str, Any],
    evaluator_fixture: Path | None = None,
) -> AttemptEvidence:
    started = time.monotonic()
    if expected_outcome not in {"TEST_FAILURE", "EXIT_ZERO"}:
        raise RuntimeError("unsupported execution expectation")
    container_fingerprint = _container_source_fingerprint(
        adapter, image, source, f"{name}-identity"
    )
    if container_fingerprint != source_identity["working_directory_fingerprint"]:
        raise RuntimeError("container-visible source identity mismatch")
    source_identity["container_visible_source_fingerprint"] = container_fingerprint
    selectors = (
        adapter.buggy_test_selectors
        if expected_outcome == "TEST_FAILURE"
        else adapter.fixed_test_selectors
    )
    command = [*adapter.evaluator_argv, *selectors]
    evaluator_fixture = evaluator_fixture or source / str(adapter.evaluator_fixture_path)
    fixture_mounts = [
        "--volume",
        f"{evaluator_fixture}:/workspace/{adapter.evaluator_fixture_path}:ro",
    ]
    marker = evaluator_fixture.parents[1] / "tests-init.py"
    if "GENERATED_TEST_PACKAGE_MARKER" in adapter.installation_plan:
        marker.write_bytes(b"")
        fixture_mounts.extend(["--volume", f"{marker}:/workspace/tests/__init__.py:ro"])
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
        f"/tox:rw,nosuid,size={adapter.sandbox.tmpfs_bytes}",
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
        f"{source}:/workspace:ro",
        *fixture_mounts,
        "--workdir",
        adapter.working_directory,
        "--env",
        "PIP_NO_INDEX=1",
        "--env",
        "PIP_FIND_LINKS=/wheelhouse",
        "--env",
        "TOX_WORK_DIR=/tox",
        image,
        *command,
    ]
    try:
        result = subprocess.run(
            docker, capture_output=True, timeout=adapter.sandbox.timeout_seconds
        )
        if result.returncode in {125, 126, 127}:
            raise subprocess.CalledProcessError(
                result.returncode, docker, output=result.stdout, stderr=result.stderr
            )
        raw = (result.stdout + result.stderr)[: adapter.sandbox.output_bytes]
        normalized = re.sub(rb"\d+(?:\.\d+)?s", b"<duration>", raw)
        normalized = re.sub(rb"/[^\s:]+", b"<path>", normalized)
        signature = hashlib.sha256(normalized).hexdigest() if result.returncode else None
        text = raw.decode("utf-8", "replace")
        failure_class = _failure_category(text, result.returncode)
        outcome = Outcome.PASS if result.returncode == 0 else Outcome.OTHER_FAILURE
        if expected_outcome == "TEST_FAILURE" and failure_class == "ASSERTION_FAILURE":
            outcome = Outcome.EXPECTED_FAILURE
        passed = sum(int(value) for value in re.findall(r"(\d+) passed", text))
        failed = sum(int(value) for value in re.findall(r"(\d+) failed", text))
        ran = sum(int(value) for value in re.findall(r"Ran (\d+) tests?", text))
        if ran and passed == 0 and failed == 0:
            passed, failed = (ran, 0) if result.returncode == 0 else (0, ran)
        return AttemptEvidence(
            outcome,
            result.returncode,
            signature,
            passed,
            failed or int(result.returncode != 0),
            min(int((time.monotonic() - started) * 1000), 1_200_000),
            len(result.stdout) + len(result.stderr) > adapter.sandbox.output_bytes,
            failure_class,
        )
    except subprocess.TimeoutExpired:
        return AttemptEvidence(Outcome.TIMEOUT, None, None, 0, 0, 1_200_000, True, "TEST_TIMEOUT")
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def _failure_category(text: str, returncode: int) -> str | None:
    """Return only a source-free allowlisted evaluator failure category."""
    if returncode == 0:
        return None
    if any(marker in text for marker in ("collected 0 items", "no tests ran", "not found:")):
        return "SELECTOR_NOT_FOUND"
    if "ImportError" in text or "ModuleNotFoundError" in text:
        return "IMPORT_ERROR"
    if "ERROR collecting" in text:
        return "COLLECTION_ERROR"
    if "PermissionError" in text or "Permission denied" in text:
        return "PERMISSION_ERROR"
    if "installation failed" in text:
        return "PROJECT_INSTALLATION_ERROR"
    if "AssertionError" in text or re.search(r"\bFAILED\b|\d+ failed", text):
        return "ASSERTION_FAILURE"
    return "TEST_PROCESS_ERROR"


def qualify(adapter: EvaluatorAdapter, root: Path, framework: Path) -> dict[str, Any]:
    task_root = root / adapter.task_id
    buggy = task_root / "buggy"
    fixed = task_root / "fixed"
    quarantine = task_root / "evaluator-quarantine"
    build = task_root / "build"
    build.mkdir(parents=True)
    failure_stage = "SOURCE_ACQUISITION"
    base_identity: dict[str, Any] | None = None
    base_size = 0
    dependency_build_status = "NOT_STARTED"
    diagnostic: dict[str, Any] | None = None
    attempts: tuple[AttemptEvidence, ...] = ()
    fixed_attempt: AttemptEvidence | None = None
    evaluator_image_identity: dict[str, str] | None = None
    buggy_identity: dict[str, Any] | None = None
    fixed_identity: dict[str, Any] | None = None
    dependency_environment_fingerprint: str | None = None
    packages: list[dict[str, str]] = []
    image_size = 0
    try:
        buggy_identity = _safe_checkout(adapter.repository, adapter.buggy_revision, buggy)
        fixed_identity = _safe_checkout(adapter.repository, adapter.fixed_revision, fixed)
        failure_stage = "IDENTITY_VERIFICATION"
        if buggy_identity["git_tree_identity"] == fixed_identity["git_tree_identity"]:
            raise RuntimeError("buggy and fixed source trees unexpectedly identical")
        _verify_identities(adapter, buggy, framework)
        evaluator_fixture = _prepare_evaluator_fixture(adapter, fixed, quarantine)
        failure_stage = "BASE_IMAGE_ACQUISITION"
        base, base_identity, base_size = _acquire_base_image(adapter, build)
        failure_stage = "DEPENDENCY_BUILD"
        image, packages, image_size, evaluator_image_identity = _build_image(adapter, build, base)
        for identity in (buggy_identity, fixed_identity):
            identity["build_context_fingerprint"] = evaluator_image_identity[
                "build_context_fingerprint"
            ]
        dependency_build_status = "COMPLETE"
        dependency_environment_fingerprint = _sha256_record(
            {
                "base_image": base_identity,
                "constraints": list(adapter.dependency_constraints),
                "distributions": packages,
                "evaluator_image": evaluator_image_identity,
            }
        )
        failure_stage = "PROJECT_INSTALL"
        _prepare_project(adapter)
        failure_stage = "BUGGY_EXECUTION"
        attempts = tuple(
            _execute(
                adapter,
                image,
                buggy,
                f"phase128f-{adapter.task_id.lower()}-buggy-{index}",
                expected_outcome="TEST_FAILURE",
                source_identity=buggy_identity,
                evaluator_fixture=evaluator_fixture,
            )
            for index in range(1, 4)
        )
        failure_stage = "FIXED_CONTROL_EXECUTION"
        fixed_attempt = _execute(
            adapter,
            image,
            fixed,
            f"phase128f-{adapter.task_id.lower()}-fixed",
            expected_outcome="EXIT_ZERO",
            source_identity=fixed_identity,
            evaluator_fixture=evaluator_fixture,
        )
        fixed_passed = fixed_attempt.outcome is Outcome.PASS
        classification = (
            Classification.FIXED_CONTROL_INFRASTRUCTURE_FAILURE
            if fixed_attempt.outcome
            in {Outcome.INFRASTRUCTURE_FAILURE, Outcome.RESOURCE_LIMIT, Outcome.TIMEOUT}
            else classify(attempts, fixed_control_passed=fixed_passed)
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError) as error:
        if len(attempts) != 3:
            attempts = tuple(
                AttemptEvidence(
                    Outcome.INFRASTRUCTURE_FAILURE,
                    None,
                    None,
                    0,
                    0,
                    0,
                    normalized_failure_class="PRE_EXECUTION_INFRASTRUCTURE_FAILURE",
                )
                for _ in range(3)
            )
        fixed_passed = False
        classification = (
            Classification.FIXED_CONTROL_INFRASTRUCTURE_FAILURE
            if failure_stage == "FIXED_CONTROL_EXECUTION"
            else Classification.INFRASTRUCTURE_FAILURE
        )
        return_code = error.returncode if isinstance(error, subprocess.CalledProcessError) else None
        stderr = error.stderr if isinstance(error, subprocess.CalledProcessError) else b""
        if isinstance(stderr, str):
            stderr = stderr.encode()
        diagnostic_bytes = stderr or str(error).encode("utf-8", "replace")
        normalized = re.sub(
            rb"/(?:home|Users|private|tmp)/[^\s:]+", b"<path>", diagnostic_bytes[:65536]
        )
        code = (
            "BASE_IMAGE_ACQUISITION_FAILED"
            if failure_stage == "BASE_IMAGE_ACQUISITION"
            else f"{failure_stage}_FAILED"
        )
        diagnostic = {
            "command_category": failure_stage,
            "failure_code": code,
            "failure_stage": failure_stage,
            "normalized_error_class": type(error).__name__,
            "normalized_stderr_sha256": hashlib.sha256(normalized).hexdigest(),
            "process_return_code": return_code,
            "retryable": failure_stage in {"SOURCE_ACQUISITION", "BASE_IMAGE_ACQUISITION"},
        }
        if failure_stage == "DEPENDENCY_BUILD":
            dependency_build_status = "FAILED"
    non_scientific = {
        Classification.INFRASTRUCTURE_FAILURE,
        Classification.FIXED_CONTROL_FAILED,
        Classification.FIXED_CONTROL_INFRASTRUCTURE_FAILURE,
        Classification.EVALUATOR_ADAPTER_INVALID,
        Classification.EVALUATOR_ENVIRONMENT_INVALID,
    }
    prior = (
        "NOT_EVALUATED_FIXED_CONTROL_REVIEW_REQUIRED"
        if classification
        in {
            Classification.FIXED_CONTROL_FAILED,
            Classification.FIXED_CONTROL_INFRASTRUCTURE_FAILURE,
        }
        else "NOT_EVALUATED_INFRASTRUCTURE_FAILURE"
        if classification is Classification.INFRASTRUCTURE_FAILURE
        else "NOT_EVALUATED_INVALID_EVALUATOR"
        if classification
        in {Classification.EVALUATOR_ADAPTER_INVALID, Classification.EVALUATOR_ENVIRONMENT_INVALID}
        else prior_evidence_status(adapter.task_id, classification)
    )
    decision = qualification_decision(classification, fixed_passed)
    if prior == "EVIDENCE_CONFLICT_REVIEW_REQUIRED":
        decision = "NOT_QUALIFIED"
    if fixed_attempt is not None:
        assert dependency_environment_fingerprint is not None
        assert evaluator_image_identity is not None
        assert fixed_identity is not None
        fixed_control = _fixed_control_record(
            adapter,
            fixed_attempt,
            dependency_environment_fingerprint,
            evaluator_image_identity,
            fixed_identity,
        )
    else:
        assert diagnostic is not None
        fixed_control = _fixed_control_not_executed(
            adapter,
            failure_stage,
            diagnostic,
            dependency_environment_fingerprint,
            evaluator_image_identity,
            fixed_identity,
        )
    buggy_signatures = {attempt.failure_signature for attempt in attempts}
    failure_classes = {attempt.normalized_failure_class for attempt in attempts}
    evaluator_validation = EvaluatorValidationStatus.VALID
    if failure_classes == {"SELECTOR_NOT_FOUND"}:
        evaluator_validation = (
            EvaluatorValidationStatus.SELECTOR_INCOMPATIBLE_ACROSS_REVISIONS
            if fixed_passed
            else EvaluatorValidationStatus.TEST_NOT_COLLECTED
        )
    elif failure_classes == {"IMPORT_ERROR"}:
        evaluator_validation = EvaluatorValidationStatus.PROJECT_NOT_INSTALLED
    elif failure_classes == {"TEST_PROCESS_ERROR"}:
        evaluator_validation = EvaluatorValidationStatus.UNSUPPORTED_EVALUATOR_LAYOUT
    buggy_result_status = (
        "BUGGY_RESULT"
        if len(attempts) == 3
        and all(attempt.outcome is Outcome.EXPECTED_FAILURE for attempt in attempts)
        and None not in buggy_signatures
        and len(buggy_signatures) == 1
        else "INFRASTRUCTURE_FAILURE"
        if any(attempt.outcome is Outcome.INFRASTRUCTURE_FAILURE for attempt in attempts)
        else "INVALID_EVALUATOR_RESULT"
    )
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
        "buggy_source_identity": buggy_identity,
        "buggy_result_status": buggy_result_status,
        "buggy_environment_fingerprint": dependency_environment_fingerprint,
        "classification": classification.value,
        "scientific_classification": (
            None if classification in non_scientific else classification.value
        ),
        "execution_status": (
            "INFRASTRUCTURE_FAILURE"
            if classification is Classification.INFRASTRUCTURE_FAILURE
            else "FIXED_CONTROL_FAILED"
            if classification
            in {
                Classification.FIXED_CONTROL_FAILED,
                Classification.FIXED_CONTROL_INFRASTRUCTURE_FAILURE,
            }
            else "INVALID_EVALUATOR_RESULT"
            if classification
            in {
                Classification.EVALUATOR_ADAPTER_INVALID,
                Classification.EVALUATOR_ENVIRONMENT_INVALID,
            }
            else "SCIENTIFIC_RESULT"
        ),
        "evaluator_validation_status": evaluator_validation.value,
        "infrastructure_diagnostic": diagnostic,
        "base_image_identity": base_identity,
        "dependency_build_status": dependency_build_status,
        "dependency_artifacts": packages,
        "fixed_control_passed": fixed_passed,
        "fixed_control": fixed_control,
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
            if fixed_attempt is not None
            else 0,
            "measured_image_bytes": image_size,
            "measured_base_image_bytes": base_size,
            "measured_task_tree_bytes": _tree_bytes(task_root),
        },
        "task_id": adapter.task_id,
    }


def cleanup(root: Path) -> None:
    containers = (
        subprocess.run(
            ["docker", "ps", "-aq", "--filter", "label=archguard.phase=12.8f"],
            capture_output=True,
            check=False,
        )
        .stdout.decode()
        .split()
    )
    if containers:
        subprocess.run(["docker", "rm", "-f", *containers], check=False, capture_output=True)
    images = (
        subprocess.run(
            ["docker", "images", "-q", "--filter", "label=archguard.phase=12.8f"],
            capture_output=True,
            check=False,
        )
        .stdout.decode()
        .split()
    )
    if images:
        subprocess.run(["docker", "image", "rm", "-f", *images], check=False, capture_output=True)
    for reference in sorted(OWNED_BASE_REFERENCES):
        subprocess.run(["docker", "image", "rm", reference], check=False, capture_output=True)
    OWNED_BASE_REFERENCES.clear()
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
