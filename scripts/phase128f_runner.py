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
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from archguard.domain.canonical import canonical_json
from archguard.domain.phase128f import (
    BATCH_A,
    BATCH_B,
    AttemptEvidence,
    Classification,
    EvaluatorAdapter,
    EvaluatorRuntimeState,
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
EVALUATOR_ROOT = "/evaluator"
RUNTIME_UID = 65532
RUNTIME_GID = 65532
PYTEST_CACHE = "/tmp/pytest-cache"
V3_RUNTIME_FIELDS = (
    "buggy_test_selectors",
    "fixed_test_selectors",
    "evaluator_fixture_path",
    "evaluator_fixture_sha256",
    "evaluator_provenance",
    "evaluator_source_type",
    "installation_plan",
    "quarantine_policy",
    "working_directory",
    "expected_framework",
)
RUNTIME_STATE_ORDER = tuple(EvaluatorRuntimeState)
PROJECT_MODULES = {"PySnooper": "pysnooper", "black": "black", "cookiecutter": "cookiecutter"}
EVALUATOR_SUPPORT_FILES = {
    "PySnooper-1": {
        "tests/__init__.py": "cf29ef59772b7309424b9229e607daca365cc178249a31f7b1c2ae748bfd1893",
        "tests/utils.py": "ae81d0d19d5b4fdb75c210d951e687f0b4c3bfb03239437240f088c818c6dc83",
    }
}


class EvaluatorPreflightError(RuntimeError):
    def __init__(self, code: str, process_return_code: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.process_return_code = process_return_code


@dataclass(frozen=True)
class ExternalSelectorResolution:
    logical_selector: str
    physical_fixture: str
    runtime_selector: str


class RuntimeTransitions:
    def __init__(self) -> None:
        self._records: list[dict[str, Any]] = []

    def reach(self, state: EvaluatorRuntimeState, operation: dict[str, Any]) -> None:
        expected = RUNTIME_STATE_ORDER[len(self._records)]
        if state is not expected:
            raise EvaluatorPreflightError(f"MISSING_TRANSITION_{expected.value}")
        self._records.append(
            {
                "index": len(self._records),
                "operation_fingerprint": _sha256_record(operation),
                "state": state.value,
            }
        )

    def evidence(self) -> dict[str, Any]:
        reached = [record["state"] for record in self._records]
        return {
            "schema": "archguard.evaluator-runtime-state-machine/v3",
            "last_reached": reached[-1] if reached else None,
            "next_required": (
                RUNTIME_STATE_ORDER[len(reached)].value
                if len(reached) < len(RUNTIME_STATE_ORDER)
                else None
            ),
            "transition_fingerprint": _sha256_record(self._records),
            "transitions": list(self._records),
        }


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
        raise ValueError("Batch B is unavailable in Phase 12.8F.4.1")
    if selection == "all":
        raise ValueError("Batch B is unavailable in Phase 12.8F.4.1")
    if selection in BATCH_B:
        raise ValueError("Batch B is unavailable in Phase 12.8F.4.1")
    return (selection,)


def _validate_runtime_canary_selection(tasks: tuple[str, ...]) -> None:
    if tasks != ("PySnooper-1",):
        raise ValueError("Phase 12.8F.4.2 runtime canary permits only PySnooper-1")


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


def _verify_source_unchanged(source: Path, identity: dict[str, Any]) -> None:
    if _working_tree_fingerprint(source) != identity["working_directory_fingerprint"]:
        raise RuntimeError("source tree changed during evaluator execution")


def _verify_evaluator_identity(adapter: EvaluatorAdapter, fixture: Path) -> str:
    if not fixture.is_file():
        raise EvaluatorPreflightError("EVALUATOR_NOT_ACQUIRED")
    fixture_sha256 = hashlib.sha256(fixture.read_bytes()).hexdigest()
    if fixture_sha256 != adapter.evaluator_fixture_sha256:
        raise EvaluatorPreflightError("EVALUATOR_IDENTITY_MISMATCH")
    return fixture_sha256


def _collection_count(output: str) -> int:
    if "COLLECTION_COUNT=" in output:
        return int(output.rsplit("COLLECTION_COUNT=", 1)[1].split()[0])
    matches = re.findall(r"(\d+) (?:test|item)s? collected", output)
    return int(matches[-1]) if matches else 0


def _collected_node(output: str, logical_selector: str) -> str:
    logical_path, separator, node = logical_selector.partition("::")
    if not separator or not node:
        raise EvaluatorPreflightError("EVALUATOR_SELECTOR_INVALID")
    compact_selector = f"::{node}"
    candidates: set[str] = set()
    for line in output.splitlines():
        value = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
        if value == compact_selector or value.endswith(logical_selector):
            candidates.add(logical_selector)
        elif "::" in value and not value.startswith(("ERROR", "WARNING")):
            candidates.add(value)
    if candidates != {logical_selector}:
        raise EvaluatorPreflightError("EVALUATOR_SELECTED_NODE_MISMATCH")
    return logical_selector


def _validate_pytest_collection(output: str, logical_selector: str) -> tuple[int, str]:
    collection_count = _collection_count(output)
    if "no tests ran" in output.lower() or collection_count not in (0, 1):
        raise EvaluatorPreflightError("EVALUATOR_NOT_COLLECTED", 0)
    collected_node = _collected_node(output, logical_selector)
    return 1, collected_node


def _pytest_collection_failure_code(output: str, project_module: str = "") -> str:
    lowered = output.lower()
    if "importerror" in lowered or "modulenotfounderror" in lowered:
        if project_module and project_module.lower() in lowered:
            return "PROJECT_IMPORT_FAILED"
        return "EVALUATOR_DEPENDENCY_MISSING"
    if "not found" in lowered or "no tests ran" in lowered:
        return "EVALUATOR_SELECTOR_NOT_FOUND"
    return "EVALUATOR_NOT_COLLECTED"


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
                "useradd --uid 65532 --gid 65532 --no-create-home evaluator && "
                "mkdir -p /tmp/archguard /tmp/home && "
                "chown -R 65532:65532 /tmp/archguard /tmp/home",
                "USER 65532:65532",
                "WORKDIR /workspace",
                "ENV HOME=/tmp/home TMPDIR=/tmp/archguard PYTHONDONTWRITEBYTECODE=1 "
                "PYTHONUNBUFFERED=1 PYTHONPATH=/workspace",
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
    runtime_wheelhouse = build_root / "runtime-wheelhouse"
    runtime_wheelhouse.mkdir()
    export_name = f"phase128f-{adapter.task_id.lower()}-wheelhouse-export"
    export_container = (
        _run(["docker", "create", "--name", export_name, tag]).stdout.decode().strip()
    )
    try:
        _run(["docker", "cp", f"{export_container}:/wheelhouse/.", str(runtime_wheelhouse)])
    finally:
        subprocess.run(["docker", "rm", "-f", export_name], capture_output=True)
    copied_packages = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in runtime_wheelhouse.iterdir()
        if path.is_file()
    }
    if copied_packages != {item["filename"]: item["sha256"] for item in packages}:
        raise RuntimeError("runtime wheelhouse identity mismatch")
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


def _quarantine_root(adapter: EvaluatorAdapter, fixture: Path) -> Path:
    assert adapter.evaluator_fixture_path is not None
    root = fixture
    for _ in PurePosixPath(adapter.evaluator_fixture_path).parts:
        root = root.parent
    return root


def _runtime_selectors(adapter: EvaluatorAdapter, expected_outcome: str) -> tuple[str, ...]:
    declared = (
        adapter.buggy_test_selectors
        if expected_outcome == "TEST_FAILURE"
        else adapter.fixed_test_selectors
    )
    assert adapter.evaluator_fixture_path is not None
    if adapter.expected_framework == "pytest":
        return tuple(
            _resolve_external_pytest_selector(
                selector,
                adapter.evaluator_fixture_path,
                EVALUATOR_ROOT,
                adapter.expected_framework,
            ).runtime_selector
            for selector in declared
        )
    if adapter.expected_framework == "tox":
        mounted_fixture = f"{EVALUATOR_ROOT}/{adapter.evaluator_fixture_path}"
        return tuple(
            selector.replace(adapter.evaluator_fixture_path, mounted_fixture, 1)
            for selector in declared
        )
    return declared


def _resolve_external_pytest_selector(
    logical_selector: str,
    fixture_relative_path: str,
    evaluator_mount_root: str,
    expected_framework: str,
) -> ExternalSelectorResolution:
    logical_path, separator, node = logical_selector.partition("::")
    fixture = PurePosixPath(fixture_relative_path)
    logical = PurePosixPath(logical_path)
    mount_root = PurePosixPath(evaluator_mount_root)
    if (
        expected_framework != "pytest"
        or not separator
        or not node
        or logical.is_absolute()
        or fixture.is_absolute()
        or not mount_root.is_absolute()
        or mount_root != PurePosixPath(EVALUATOR_ROOT)
        or any(part in {"", ".", ".."} for part in logical.parts)
        or any(part in {"", ".", ".."} for part in fixture.parts)
        or logical != fixture
    ):
        raise EvaluatorPreflightError("EVALUATOR_SELECTOR_OUTSIDE_ROOT")
    physical = mount_root / fixture
    if not physical.is_relative_to(mount_root) or physical == mount_root:
        raise EvaluatorPreflightError("EVALUATOR_SELECTOR_OUTSIDE_ROOT")
    return ExternalSelectorResolution(
        logical_selector=logical_selector,
        physical_fixture=physical.as_posix(),
        runtime_selector=f"{physical.as_posix()}::{node}",
    )


def _runtime_argv(adapter: EvaluatorAdapter, expected_outcome: str) -> tuple[str, ...]:
    selectors = _runtime_selectors(adapter, expected_outcome)
    if adapter.expected_framework == "pytest":
        return (*adapter.evaluator_argv, "-o", f"cache_dir={PYTEST_CACHE}", *selectors)
    if adapter.expected_framework == "tox":
        return (
            *adapter.evaluator_argv,
            "-c",
            f"{EVALUATOR_ROOT}/tox-runtime.ini",
            "-e",
            "py36",
            "--",
            *selectors,
        )
    return (*adapter.evaluator_argv, *selectors)


def _execution_plan(adapter: EvaluatorAdapter, fixture: Path | None = None) -> dict[str, Any]:
    if adapter.schema != "archguard.evaluator-adapter/v3" or adapter.review_status != "REVIEWED":
        raise EvaluatorPreflightError("UNREVIEWED_ADAPTER")
    if adapter.quarantine_policy != "READ_ONLY_FIXED_TEST_NO_AGENT_ACCESS":
        raise EvaluatorPreflightError("QUARANTINE_POLICY_INVALID")
    if adapter.evaluator_source_type != "FIXED_REVISION_QUARANTINED_TEST":
        raise EvaluatorPreflightError("EVALUATOR_SOURCE_TYPE_UNSUPPORTED")
    if adapter.evaluator_fixture_path is None:
        raise EvaluatorPreflightError("EVALUATOR_FIXTURE_PATH_MISSING")
    if not adapter.evaluator_provenance.startswith(f"BugsInPy@{BUGSINPY_REVISION}:"):
        raise EvaluatorPreflightError("EVALUATOR_PROVENANCE_INVALID")
    if adapter.expected_framework != adapter.evaluator_argv[2]:
        raise EvaluatorPreflightError("FRAMEWORK_COMMAND_MISMATCH")
    supported_plans = {
        "OFFICIAL_SETUP",
        "PYTHONPATH_SOURCE",
        "GENERATED_TEST_PACKAGE_MARKER",
        "OFFLINE_TOX",
    }
    if (
        not set(adapter.installation_plan) <= supported_plans
        or "OFFICIAL_SETUP" not in adapter.installation_plan
    ):
        raise EvaluatorPreflightError("INSTALLATION_PLAN_UNSUPPORTED")
    consumers = {
        "buggy_test_selectors": "runtime-selector:buggy",
        "fixed_test_selectors": "runtime-selector:fixed",
        "evaluator_fixture_path": "dedicated-read-only-mount",
        "evaluator_fixture_sha256": "host-and-container-identity-check",
        "evaluator_provenance": "reviewed-plan-binding",
        "evaluator_source_type": "quarantine-acquisition",
        "installation_plan": "project-and-framework-preflight",
        "quarantine_policy": "mount-policy-validation",
        "working_directory": "container-workdir",
        "expected_framework": "framework-command-validation",
    }
    if set(consumers) != set(V3_RUNTIME_FIELDS):
        raise EvaluatorPreflightError("V3_FIELD_IGNORED")
    host_hash = hashlib.sha256(fixture.read_bytes()).hexdigest() if fixture is not None else None
    if host_hash is not None and host_hash != adapter.evaluator_fixture_sha256:
        raise EvaluatorPreflightError("EVALUATOR_IDENTITY_MISMATCH")
    selector_resolutions = []
    if adapter.expected_framework == "pytest":
        for role, logical_selectors in (
            ("buggy", adapter.buggy_test_selectors),
            ("fixed", adapter.fixed_test_selectors),
        ):
            for logical_selector in logical_selectors:
                resolution = _resolve_external_pytest_selector(
                    logical_selector,
                    adapter.evaluator_fixture_path,
                    EVALUATOR_ROOT,
                    adapter.expected_framework,
                )
                selector_resolutions.append(
                    {
                        "logical_selector_fingerprint": _sha256_record(resolution.logical_selector),
                        "physical_fixture_fingerprint": _sha256_record(resolution.physical_fixture),
                        "role": role,
                        "runtime_selector_fingerprint": _sha256_record(resolution.runtime_selector),
                    }
                )
    return {
        "schema": "archguard.phase-12.8f4-1-execution-plan/v1",
        "adapter_fingerprint": adapter.fingerprint,
        "adapter_schema": adapter.schema,
        "applied_buggy_selector_fingerprint": _sha256_record(
            list(_runtime_selectors(adapter, "TEST_FAILURE"))
        ),
        "applied_fixed_selector_fingerprint": _sha256_record(
            list(_runtime_selectors(adapter, "EXIT_ZERO"))
        ),
        "applied_fixture_fingerprint": adapter.evaluator_fixture_sha256,
        "applied_installation_plan_fingerprint": _sha256_record(list(adapter.installation_plan)),
        "applied_working_directory_fingerprint": _sha256_record(adapter.working_directory),
        "applied_framework": adapter.expected_framework,
        "expected_buggy_outcome": adapter.expected_buggy_outcome,
        "expected_fixed_outcome": adapter.fixed_success,
        "fixture_mount_destination_fingerprint": _sha256_record(
            f"{EVALUATOR_ROOT}/{adapter.evaluator_fixture_path}"
        ),
        "host_fixture_fingerprint": host_hash,
        "runtime_consumers": consumers,
        "selector_resolution_fingerprint": _sha256_record(selector_resolutions),
        "selector_resolutions": selector_resolutions,
        "v3_plan_validation": "VALID",
    }


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
        "project_installation_mode": (
            "PYTHONPATH_SOURCE"
            if "PYTHONPATH_SOURCE" in adapter.installation_plan
            else "DEPENDENCIES_ONLY_NO_TARGET_INSTALL"
        ),
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


def _prepare_project(adapter: EvaluatorAdapter) -> dict[str, Any]:
    """Establish the explicit, source-free project import environment."""
    if not adapter.evaluator_argv:
        raise RuntimeError("adapter has no reviewed evaluator")
    if adapter.project not in PROJECT_MODULES:
        raise EvaluatorPreflightError("PROJECT_MODULE_NOT_ALLOWLISTED")
    if adapter.task_id == "PySnooper-1" and "PYTHONPATH_SOURCE" not in adapter.installation_plan:
        raise EvaluatorPreflightError("PYTHONPATH_SOURCE_REQUIRED")
    if adapter.working_directory != "/workspace":
        raise EvaluatorPreflightError("PROJECT_WORKDIR_INVALID")
    return {
        "environment_fingerprint": _sha256_record(
            {"home": "/tmp/home", "pythonpath": "/workspace", "workdir": "/workspace"}
        ),
        "installation_mode": (
            "PYTHONPATH_SOURCE"
            if "PYTHONPATH_SOURCE" in adapter.installation_plan
            else adapter.installation_plan[-1]
        ),
        "module_name_fingerprint": _sha256_record(PROJECT_MODULES[adapter.project]),
    }


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
    for relative, expected_sha256 in EVALUATOR_SUPPORT_FILES.get(adapter.task_id, {}).items():
        support_source = fixed / relative
        support_destination = quarantine / relative
        if (
            not support_source.is_file()
            or support_source.is_symlink()
            or hashlib.sha256(support_source.read_bytes()).hexdigest() != expected_sha256
        ):
            raise RuntimeError("external evaluator support identity mismatch")
        support_destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(support_source, support_destination)
        if hashlib.sha256(support_destination.read_bytes()).hexdigest() != expected_sha256:
            raise RuntimeError("external evaluator support identity mismatch")
    if "GENERATED_TEST_PACKAGE_MARKER" in adapter.installation_plan:
        marker = quarantine / "tests/__init__.py"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_bytes(b"")
    if "OFFLINE_TOX" in adapter.installation_plan:
        (quarantine / "tox-runtime.ini").write_text(
            "[tox]\nenvlist = py36\nskipsdist = true\n"
            "[testenv]\nsitepackages = true\nskip_install = true\n"
            "passenv = PYTHONPATH PIP_NO_INDEX PIP_FIND_LINKS\n"
            "commands = python -m pytest {posargs}\n",
            encoding="utf-8",
        )
    return destination


def _sandbox_prefix(
    adapter: EvaluatorAdapter,
    image: str,
    source: Path,
    evaluator_root: Path,
    name: str,
    wheelhouse_root: Path | None = None,
) -> list[str]:
    source_resolved = source.resolve()
    evaluator_resolved = evaluator_root.resolve()
    if evaluator_resolved.is_relative_to(source_resolved) or source_resolved.is_relative_to(
        evaluator_resolved
    ):
        raise EvaluatorPreflightError("INVALID_NESTED_EVALUATOR_MOUNT")
    wheelhouse_root = wheelhouse_root or evaluator_root.parent / "build" / "runtime-wheelhouse"
    wheelhouse_root.mkdir(parents=True, exist_ok=True)
    return [
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
        f"/tmp:rw,noexec,nosuid,nodev,size={adapter.sandbox.tmpfs_bytes},"
        f"mode=1777,uid={RUNTIME_UID},gid={RUNTIME_GID}",
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
        f"{RUNTIME_UID}:{RUNTIME_GID}",
        "--volume",
        f"{source}:/workspace:ro",
        "--volume",
        f"{evaluator_root}:{EVALUATOR_ROOT}:ro",
        "--volume",
        f"{wheelhouse_root}:/wheelhouse:ro",
        "--workdir",
        adapter.working_directory,
        "--env",
        "PYTHONPATH=/workspace",
        "--env",
        "HOME=/tmp/home",
        "--env",
        "TMPDIR=/tmp/archguard",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        "--env",
        "PYTHONPYCACHEPREFIX=/tmp/archguard/pycache",
        "--env",
        "PIP_NO_INDEX=1",
        "--env",
        "PIP_FIND_LINKS=/wheelhouse",
        "--env",
        "TOX_WORK_DIR=/tox",
        "--env",
        "TOXENV=py36",
        image,
        "/bin/sh",
        "-c",
        'umask 077; mkdir -p /tmp/home /tmp/archguard /tmp/pytest-cache; exec "$@"',
        "archguard-runtime-init",
    ]


def _validate_mount_probe(probe: dict[str, Any], expected_fixture_sha256: str) -> None:
    required = {
        "source_exists": True,
        "evaluator_exists": True,
        "fixture_exists": True,
        "mounts_distinct": True,
        "source_read_only": True,
        "evaluator_read_only": True,
        "docker_socket_absent": True,
        "network_disabled": True,
    }
    for field, expected in required.items():
        if probe.get(field) is not expected:
            raise EvaluatorPreflightError(f"MOUNT_PROBE_{field.upper()}")
    if probe.get("fixture_sha256") != expected_fixture_sha256:
        raise EvaluatorPreflightError("EVALUATOR_IDENTITY_MISMATCH")


def _validate_writable_probe(probe: dict[str, Any]) -> None:
    paths = probe.get("writable_paths")
    if not isinstance(paths, list) or len(paths) != 4:
        raise EvaluatorPreflightError("WRITABLE_PROBE_INCOMPLETE")
    required = {
        "cleanup": True,
        "exists": True,
        "mount_type_category": "tmpfs",
        "not_symlink": True,
        "outside_protected_mounts": True,
        "ownership_compatible": True,
        "writable": True,
    }
    for path in paths:
        if not isinstance(path, dict):
            raise EvaluatorPreflightError("WRITABLE_PROBE_INVALID")
        fingerprint = path.get("role_fingerprint")
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise EvaluatorPreflightError("WRITABLE_PROBE_ROLE_FINGERPRINT")
        for field, expected in required.items():
            if path.get(field) != expected:
                raise EvaluatorPreflightError(f"WRITABLE_PROBE_{field.upper()}")


def _validate_tmpfs_created(probe: dict[str, Any]) -> None:
    if probe.get("tmpfs_created") is not True:
        raise EvaluatorPreflightError("TMPFS_NOT_CREATED")


def _mount_probe(
    adapter: EvaluatorAdapter,
    image: str,
    source: Path,
    evaluator_root: Path,
    name: str,
) -> dict[str, Any]:
    assert adapter.evaluator_fixture_path is not None
    assert adapter.evaluator_fixture_sha256 is not None
    mounted_fixture = f"{EVALUATOR_ROOT}/{adapter.evaluator_fixture_path}"
    script = """import hashlib,json,os,pathlib,secrets,stat,sys
fixture=pathlib.Path(sys.argv[1]); points={}
for line in pathlib.Path('/proc/self/mountinfo').read_text().splitlines():
 parts=line.split(); points[parts[4]]=parts
def readonly(point): return point in points and 'ro' in points[point][5].split(',')
def mount_type(path):
 matches=[point for point in points if path==point or path.startswith(point.rstrip('/')+'/')]
 if not matches: return 'unknown'
 parts=points[max(matches,key=len)]; separator=parts.index('-'); return parts[separator+1]
def writable(role,path):
 target=None; exists=path.is_dir(); linked=path.is_symlink(); compatible=False; worked=False
 try:
  metadata=path.stat(); mode=metadata.st_mode
  compatible=((metadata.st_uid==os.geteuid() and bool(mode & stat.S_IWUSR)) or
   (metadata.st_gid==os.getegid() and bool(mode & stat.S_IWGRP)) or bool(mode & stat.S_IWOTH))
  target=path/('.archguard-'+secrets.token_hex(12))
  descriptor=os.open(target,os.O_CREAT|os.O_EXCL|os.O_RDWR|os.O_NOFOLLOW,0o600)
  try:
   payload=b'archguard'; os.write(descriptor,payload); os.fsync(descriptor)
   worked=os.fstat(descriptor).st_size==len(payload)
  finally: os.close(descriptor)
 except OSError: pass
 finally:
  if target is not None:
   try: target.unlink()
   except OSError: pass
 return {'role_fingerprint':hashlib.sha256(role.encode()).hexdigest(),'exists':exists,
 'not_symlink':not linked,'writable':worked,'mount_type_category':mount_type(str(path)),
 'ownership_compatible':compatible,'cleanup':target is None or not target.exists(),
 'outside_protected_mounts':not any(str(path.resolve()).startswith(root+'/') or
 str(path.resolve())==root for root in ('/workspace','/evaluator','/wheelhouse'))}
source=pathlib.Path('/workspace'); evaluator=pathlib.Path('/evaluator')
write_results=[writable(role,pathlib.Path(path)) for role,path in (
('temporary-root','/tmp'),('home','/tmp/home'),('temporary-data','/tmp/archguard'),
('pytest-cache','/tmp/pytest-cache'))]
body={'source_exists':source.is_dir(),'evaluator_exists':evaluator.is_dir(),
'fixture_exists':fixture.is_file(),
'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest() if fixture.is_file() else None,
'mounts_distinct':('/workspace' in points and '/evaluator' in points and
points['/workspace'][0]!=points['/evaluator'][0]),
'source_read_only':readonly('/workspace'),'evaluator_read_only':readonly('/evaluator'),
'tmpfs_created':mount_type('/tmp')=='tmpfs','writable_paths':write_results,
'docker_socket_absent':not pathlib.Path('/var/run/docker.sock').exists(),
'network_disabled':{path.name for path in pathlib.Path('/sys/class/net').iterdir()} <= {'lo'}}
print(json.dumps(body,sort_keys=True,separators=(',',':')))"""
    command = _sandbox_prefix(adapter, image, source, evaluator_root, name) + [
        "python",
        "-c",
        script,
        mounted_fixture,
    ]
    result = subprocess.run(command, capture_output=True, timeout=120)
    try:
        if result.returncode != 0:
            raise EvaluatorPreflightError("MOUNT_PROBE_FAILED")
        probe = json.loads(result.stdout)
        if not isinstance(probe, dict):
            raise EvaluatorPreflightError("MOUNT_PROBE_INVALID")
        container_source_fingerprint = _container_source_fingerprint(
            adapter, image, source, f"{name}-source-identity"
        )
        if container_source_fingerprint != _working_tree_fingerprint(source):
            raise EvaluatorPreflightError("SOURCE_IDENTITY_MISMATCH")
        probe["container_source_fingerprint"] = container_source_fingerprint
        return probe
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def _preflight(
    adapter: EvaluatorAdapter,
    image: str,
    source: Path,
    name: str,
    evaluator_fixture: Path,
    transitions: RuntimeTransitions | None = None,
) -> dict[str, Any]:
    evaluator_root = _quarantine_root(adapter, evaluator_fixture)
    assert adapter.evaluator_fixture_path is not None
    assert adapter.evaluator_fixture_sha256 is not None
    mounted_fixture = f"{EVALUATOR_ROOT}/{adapter.evaluator_fixture_path}"
    if adapter.project not in PROJECT_MODULES:
        raise EvaluatorPreflightError("PROJECT_MODULE_NOT_ALLOWLISTED")
    project_module = PROJECT_MODULES[adapter.project]
    topology = _mount_probe(adapter, image, source, evaluator_root, f"{name}-mount-probe")
    _validate_tmpfs_created(topology)
    if transitions is not None:
        transitions.reach(
            EvaluatorRuntimeState.TMPFS_CREATED,
            {
                "mount_type_category": "tmpfs",
                "options_fingerprint": _sha256_record(
                    {
                        "gid": RUNTIME_GID,
                        "mode": "1777",
                        "noexec": True,
                        "size": adapter.sandbox.tmpfs_bytes,
                        "uid": RUNTIME_UID,
                    }
                ),
            },
        )
    _validate_writable_probe(topology)
    if transitions is not None:
        transitions.reach(
            EvaluatorRuntimeState.WRITABLE_PATHS_VERIFIED,
            {"path_roles": topology["writable_paths"]},
        )
    _validate_mount_probe(topology, adapter.evaluator_fixture_sha256)
    if transitions is not None:
        transitions.reach(
            EvaluatorRuntimeState.SOURCE_MOUNTED,
            {
                "identity": topology["container_source_fingerprint"],
                "mount": "/workspace",
                "read_only": topology["source_read_only"],
            },
        )
        transitions.reach(
            EvaluatorRuntimeState.EVALUATOR_MOUNTED,
            {
                "fixture_sha256": topology["fixture_sha256"],
                "mount": EVALUATOR_ROOT,
            },
        )
    import_name = f"{name}-project-import"
    import_command = _sandbox_prefix(adapter, image, source, evaluator_root, import_name) + [
        "python",
        "-c",
        f"import {project_module}",
    ]
    try:
        import_result = subprocess.run(
            import_command, capture_output=True, timeout=adapter.sandbox.timeout_seconds
        )
        if import_result.returncode != 0:
            raise EvaluatorPreflightError("PROJECT_IMPORT_FAILED")
    finally:
        subprocess.run(["docker", "rm", "-f", import_name], capture_output=True)
    if transitions is not None:
        transitions.reach(
            EvaluatorRuntimeState.PROJECT_IMPORT_VERIFIED,
            {
                "environment": _sha256_record(
                    {"cwd": adapter.working_directory, "pythonpath": "/workspace"}
                ),
                "exit_status": 0,
                "module_name_fingerprint": _sha256_record(project_module),
            },
        )
    if adapter.expected_framework != "pytest":
        evaluator_import_name = f"{name}-evaluator-import"
        evaluator_import_command = _sandbox_prefix(
            adapter, image, source, evaluator_root, evaluator_import_name
        ) + ["python", "-c", "import runpy,sys; runpy.run_path(sys.argv[1])", mounted_fixture]
        try:
            evaluator_import = subprocess.run(
                evaluator_import_command,
                capture_output=True,
                timeout=adapter.sandbox.timeout_seconds,
            )
            if evaluator_import.returncode != 0:
                raise EvaluatorPreflightError("EVALUATOR_IMPORT_FAILED")
        finally:
            subprocess.run(["docker", "rm", "-f", evaluator_import_name], capture_output=True)
        if transitions is not None:
            transitions.reach(
                EvaluatorRuntimeState.EVALUATOR_IMPORT_VERIFIED,
                {"exit_status": 0, "fixture_sha256": adapter.evaluator_fixture_sha256},
            )
    selector_resolution: ExternalSelectorResolution | None = None
    container_hash: str | None = None
    if adapter.expected_framework == "pytest":
        if len(adapter.buggy_test_selectors) != 1:
            raise EvaluatorPreflightError("EVALUATOR_SELECTOR_INVALID")
        selector_resolution = _resolve_external_pytest_selector(
            adapter.buggy_test_selectors[0],
            adapter.evaluator_fixture_path,
            EVALUATOR_ROOT,
            adapter.expected_framework,
        )
        container_hash_command = _sandbox_prefix(
            adapter, image, source, evaluator_root, f"{name}-identity"
        ) + [
            "python",
            "-c",
            "import hashlib,pathlib,sys; "
            "path=pathlib.Path(sys.argv[1]); "
            "assert path.is_file() and not path.is_symlink(); "
            "print(hashlib.sha256(path.read_bytes()).hexdigest())",
            selector_resolution.physical_fixture,
        ]
        identity = subprocess.run(container_hash_command, capture_output=True, timeout=120)
        if identity.returncode != 0:
            raise EvaluatorPreflightError("EVALUATOR_IDENTITY_UNREADABLE", identity.returncode)
        container_hash = identity.stdout.decode("ascii").strip()
        if container_hash != adapter.evaluator_fixture_sha256:
            raise EvaluatorPreflightError("EVALUATOR_IDENTITY_MISMATCH", identity.returncode)
        preflight_argv = [
            "python",
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-o",
            f"cache_dir={PYTEST_CACHE}",
            selector_resolution.runtime_selector,
        ]
    elif adapter.expected_framework == "unittest":
        selector = _runtime_selectors(adapter, "TEST_FAILURE")[0]
        preflight_argv = [
            "python",
            "-c",
            "import importlib,unittest,sys; "
            f"importlib.import_module('{project_module}'); "
            f"suite=unittest.defaultTestLoader.loadTestsFromName('{selector}'); "
            "count=suite.countTestCases(); "
            "print('COLLECTION_COUNT='+str(count)); sys.exit(count != 1)",
        ]
    else:
        preflight_argv = [*_runtime_argv(adapter, "TEST_FAILURE"), "--collect-only"]
    command = _sandbox_prefix(adapter, image, source, evaluator_root, name) + preflight_argv
    try:
        collection_started = time.monotonic()
        result = subprocess.run(
            command, capture_output=True, timeout=adapter.sandbox.timeout_seconds
        )
        collection_duration_milliseconds = int((time.monotonic() - collection_started) * 1000)
        raw_collection_output = result.stdout + result.stderr
        collection_output_truncated = len(raw_collection_output) > adapter.sandbox.output_bytes
        bounded_collection_output = raw_collection_output[: adapter.sandbox.output_bytes].decode(
            "utf-8", "replace"
        )
        if result.returncode != 0:
            text = bounded_collection_output
            if adapter.expected_framework == "tox":
                code = (
                    "OFFLINE_DEPENDENCY_MISSING"
                    if "No matching distribution" in text or "Could not find" in text
                    else "TOX_ENVIRONMENT_MISSING"
                    if "InterpreterNotFound" in text
                    else "TOX_CONFIGURATION_INVALID"
                )
            else:
                code = _pytest_collection_failure_code(text, project_module)
            raise EvaluatorPreflightError(code, result.returncode)
        output = bounded_collection_output
        declared_selectors = (
            adapter.buggy_test_selectors
            if adapter.expected_framework == "pytest"
            else _runtime_selectors(adapter, "TEST_FAILURE")
        )
        if len(declared_selectors) != 1:
            raise EvaluatorPreflightError("EVALUATOR_NOT_COLLECTED", 0)
        if adapter.expected_framework == "pytest":
            collection_count, collected_node = _validate_pytest_collection(
                output, declared_selectors[0]
            )
        else:
            collection_count = _collection_count(output)
            if collection_count != 1:
                raise EvaluatorPreflightError("EVALUATOR_NOT_COLLECTED", 0)
            collected_node = declared_selectors[0]
        if container_hash is None:
            container_hash_command = _sandbox_prefix(
                adapter, image, source, evaluator_root, f"{name}-identity"
            ) + [
                "python",
                "-c",
                "import hashlib,pathlib,sys; "
                "print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())",
                mounted_fixture,
            ]
            identity = subprocess.run(container_hash_command, capture_output=True, timeout=120)
            if identity.returncode != 0:
                raise EvaluatorPreflightError("EVALUATOR_IDENTITY_UNREADABLE", identity.returncode)
            container_hash = identity.stdout.decode("ascii").strip()
            if container_hash != adapter.evaluator_fixture_sha256:
                raise EvaluatorPreflightError("EVALUATOR_IDENTITY_MISMATCH", identity.returncode)
        if transitions is not None:
            if adapter.expected_framework == "pytest":
                transitions.reach(
                    EvaluatorRuntimeState.EVALUATOR_IMPORT_VERIFIED,
                    {
                        "collection_exit_status": 0,
                        "collection_duration_milliseconds": collection_duration_milliseconds,
                        "fixture_sha256": container_hash,
                        "loader": "pytest-collection",
                    },
                )
            transitions.reach(
                EvaluatorRuntimeState.TEST_COLLECTED,
                {
                    "collection_count": collection_count,
                    "collection_duration_milliseconds": collection_duration_milliseconds,
                    "collected_node_fingerprint": _sha256_record(collected_node),
                    "fixture_sha256": container_hash,
                    "logical_selector_fingerprint": _sha256_record(list(declared_selectors)),
                    "resolved_selector_fingerprint": _sha256_record(
                        list(_runtime_selectors(adapter, "TEST_FAILURE"))
                    ),
                    "output_truncated": collection_output_truncated,
                },
            )
        return {
            "collection_count": collection_count,
            "collection_duration_milliseconds": collection_duration_milliseconds,
            "collection_exit_code": result.returncode,
            "collection_output_truncated": collection_output_truncated,
            "container_visible_fixture_fingerprint": container_hash,
            "evaluator_fixture_mounted": True,
            "evaluator_fixture_identity_match": True,
            "evaluator_import_verified": True,
            "collected_node_fingerprint": _sha256_record(collected_node),
            "fixture_mount_root_fingerprint": _sha256_record(EVALUATOR_ROOT),
            "logical_selector_fingerprint": _sha256_record(list(declared_selectors)),
            "mount_topology_verified": True,
            "project_import_verified": True,
            "project_installation_preflight": "PASSED",
            "selector_fingerprint": _sha256_record(
                list(_runtime_selectors(adapter, "TEST_FAILURE"))
            ),
            "tox_environment_fingerprint": (
                _sha256_record({"environment": "py36", "wheelhouse": "/wheelhouse"})
                if adapter.expected_framework == "tox"
                else None
            ),
        }
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


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
        "EVALUATOR_PREFLIGHT": FixedControlStage.TEST_COLLECTION,
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
        "project_installation_mode": (
            "PYTHONPATH_SOURCE"
            if "PYTHONPATH_SOURCE" in adapter.installation_plan
            else "DEPENDENCIES_ONLY_NO_TARGET_INSTALL"
        ),
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
    command = list(_runtime_argv(adapter, expected_outcome))
    evaluator_fixture = evaluator_fixture or source / str(adapter.evaluator_fixture_path)
    evaluator_root = _quarantine_root(adapter, evaluator_fixture)
    docker = _sandbox_prefix(adapter, image, source, evaluator_root, name) + command
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
    execution_plan: dict[str, Any] | None = None
    buggy_preflight: dict[str, Any] | None = None
    fixed_preflight: dict[str, Any] | None = None
    transitions = RuntimeTransitions()
    try:
        execution_plan = _execution_plan(adapter)
        transitions.reach(
            EvaluatorRuntimeState.PLAN_VALIDATED,
            {"adapter_fingerprint": adapter.fingerprint, "schema": adapter.schema},
        )
        buggy_identity = _safe_checkout(adapter.repository, adapter.buggy_revision, buggy)
        fixed_identity = _safe_checkout(adapter.repository, adapter.fixed_revision, fixed)
        transitions.reach(
            EvaluatorRuntimeState.SOURCE_ACQUIRED,
            {
                "buggy_revision": buggy_identity["checked_out_head"],
                "fixed_revision": fixed_identity["checked_out_head"],
            },
        )
        failure_stage = "IDENTITY_VERIFICATION"
        if buggy_identity["git_tree_identity"] == fixed_identity["git_tree_identity"]:
            raise RuntimeError("buggy and fixed source trees unexpectedly identical")
        _verify_identities(adapter, buggy, framework)
        transitions.reach(
            EvaluatorRuntimeState.SOURCE_IDENTITY_VERIFIED,
            {
                "buggy_tree": buggy_identity["git_tree_identity"],
                "fixed_tree": fixed_identity["git_tree_identity"],
            },
        )
        evaluator_fixture = _prepare_evaluator_fixture(adapter, fixed, quarantine)
        transitions.reach(
            EvaluatorRuntimeState.EVALUATOR_ACQUIRED,
            {"provenance_fingerprint": _sha256_record(adapter.evaluator_provenance)},
        )
        fixture_sha256 = _verify_evaluator_identity(adapter, evaluator_fixture)
        execution_plan["host_fixture_fingerprint"] = fixture_sha256
        transitions.reach(
            EvaluatorRuntimeState.EVALUATOR_IDENTITY_VERIFIED,
            {"fixture_sha256": fixture_sha256},
        )
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
        installation = _prepare_project(adapter)
        transitions.reach(EvaluatorRuntimeState.INSTALLATION_PREPARED, installation)
        failure_stage = "EVALUATOR_PREFLIGHT"
        buggy_preflight = _preflight(
            adapter,
            image,
            buggy,
            f"phase128f-{adapter.task_id.lower()}-buggy-preflight",
            evaluator_fixture,
            transitions,
        )
        fixed_preflight = _preflight(
            adapter,
            image,
            fixed,
            f"phase128f-{adapter.task_id.lower()}-fixed-preflight",
            evaluator_fixture,
        )
        execution_plan.update(
            {
                "buggy_preflight": buggy_preflight,
                "fixed_preflight": fixed_preflight,
                "fixture_bytes_identical": (
                    buggy_preflight["container_visible_fixture_fingerprint"]
                    == fixed_preflight["container_visible_fixture_fingerprint"]
                    == execution_plan["host_fixture_fingerprint"]
                ),
            }
        )
        if not execution_plan["fixture_bytes_identical"]:
            raise EvaluatorPreflightError("EVALUATOR_IDENTITY_MISMATCH")
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
        attempt_signatures = {attempt.failure_signature for attempt in attempts}
        if (
            len(attempts) != 3
            or any(attempt.outcome is not Outcome.EXPECTED_FAILURE for attempt in attempts)
            or None in attempt_signatures
            or len(attempt_signatures) != 1
        ):
            raise EvaluatorPreflightError("BUGGY_SCIENTIFIC_ATTEMPTS_INVALID")
        transitions.reach(
            EvaluatorRuntimeState.BUGGY_EXECUTED,
            {"attempt_count": 3, "failure_signature": next(iter(attempt_signatures))},
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
        _verify_source_unchanged(buggy, buggy_identity)
        _verify_source_unchanged(fixed, fixed_identity)
        fixed_passed = fixed_attempt.outcome is Outcome.PASS
        if fixed_passed and fixed_attempt.tests_passed == 1 and fixed_attempt.tests_failed == 0:
            transitions.reach(
                EvaluatorRuntimeState.FIXED_EXECUTED,
                {"exit_code": fixed_attempt.exit_code, "tests_failed": 0, "tests_passed": 1},
            )
        shutil.rmtree(quarantine, ignore_errors=True)
        if transitions.evidence()["last_reached"] == EvaluatorRuntimeState.FIXED_EXECUTED.value:
            transitions.reach(
                EvaluatorRuntimeState.CLEANED,
                {"evaluator_quarantine_removed": not quarantine.exists()},
            )
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
        adapter_failure_codes = {
            "EVALUATOR_PROVENANCE_INVALID",
            "EVALUATOR_SOURCE_TYPE_UNSUPPORTED",
            "FRAMEWORK_COMMAND_MISMATCH",
            "INSTALLATION_PLAN_UNSUPPORTED",
            "QUARANTINE_POLICY_INVALID",
            "UNREVIEWED_ADAPTER",
            "V3_FIELD_IGNORED",
        }
        classification = (
            Classification.EVALUATOR_ADAPTER_INVALID
            if isinstance(error, EvaluatorPreflightError) and error.code in adapter_failure_codes
            else Classification.EVALUATOR_ENVIRONMENT_INVALID
            if isinstance(error, EvaluatorPreflightError)
            else Classification.FIXED_CONTROL_INFRASTRUCTURE_FAILURE
            if failure_stage == "FIXED_CONTROL_EXECUTION"
            else Classification.INFRASTRUCTURE_FAILURE
        )
        return_code = (
            error.returncode
            if isinstance(error, subprocess.CalledProcessError)
            else error.process_return_code
            if isinstance(error, EvaluatorPreflightError)
            else None
        )
        stderr = error.stderr if isinstance(error, subprocess.CalledProcessError) else b""
        if isinstance(stderr, str):
            stderr = stderr.encode()
        diagnostic_bytes = stderr or str(error).encode("utf-8", "replace")
        normalized = re.sub(
            rb"/(?:home|Users|private|tmp)/[^\s:]+", b"<path>", diagnostic_bytes[:65536]
        )
        code = (
            error.code
            if isinstance(error, EvaluatorPreflightError)
            else "BASE_IMAGE_ACQUISITION_FAILED"
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
    completed_runtime_canary = (
        adapter.task_id == "PySnooper-1"
        and classification is Classification.STABLE
        and transitions.evidence()["last_reached"] == EvaluatorRuntimeState.CLEANED.value
    )
    prior = (
        "PRIOR_EVALUATOR_NOT_COMPARABLE"
        if completed_runtime_canary
        else "NOT_EVALUATED_FIXED_CONTROL_REVIEW_REQUIRED"
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
    preflight_statuses = {
        "TOX_ENVIRONMENT_MISSING": EvaluatorValidationStatus.TOX_ENVIRONMENT_MISSING,
        "TOX_CONFIGURATION_INVALID": EvaluatorValidationStatus.TOX_CONFIGURATION_INVALID,
        "OFFLINE_DEPENDENCY_MISSING": EvaluatorValidationStatus.OFFLINE_DEPENDENCY_MISSING,
        "EVALUATOR_NOT_COLLECTED": EvaluatorValidationStatus.EVALUATOR_NOT_COLLECTED,
        "EVALUATOR_SELECTOR_NOT_FOUND": EvaluatorValidationStatus.TEST_NOT_COLLECTED,
        "EVALUATOR_DEPENDENCY_MISSING": EvaluatorValidationStatus.DEPENDENCY_MISSING,
        "PROJECT_IMPORT_FAILED": EvaluatorValidationStatus.PROJECT_NOT_INSTALLED,
    }
    if diagnostic is not None and diagnostic["failure_code"] in preflight_statuses:
        evaluator_validation = preflight_statuses[diagnostic["failure_code"]]
    elif classification is Classification.EVALUATOR_ADAPTER_INVALID:
        evaluator_validation = EvaluatorValidationStatus.EVALUATOR_ADAPTER_INVALID
    elif classification is Classification.EVALUATOR_ENVIRONMENT_INVALID:
        evaluator_validation = EvaluatorValidationStatus.EVALUATOR_ENVIRONMENT_INVALID
    elif failure_classes == {"SELECTOR_NOT_FOUND"}:
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
        "execution_plan": execution_plan,
        "runtime_state_machine": transitions.evidence(),
        "buggy_preflight": buggy_preflight,
        "fixed_preflight": fixed_preflight,
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
    parser.add_argument("--runtime-canary", action="store_true")
    parser.add_argument("--external-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.uname().sysname != "Linux" or os.uname().machine != "x86_64":
        raise SystemExit("native Linux x86_64 required")
    registry = json.loads(args.adapters.read_text(encoding="utf-8"))
    adapters = {_adapter(value).task_id: _adapter(value) for value in registry["adapters"]}
    tasks = _tasks(args.selection)
    if args.runtime_canary:
        try:
            _validate_runtime_canary_selection(tasks)
        except ValueError as error:
            raise SystemExit(str(error)) from error
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
