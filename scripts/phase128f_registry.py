#!/usr/bin/env python3
"""Regenerate the canonical Phase 12.8F evaluator-adapter registry."""

import argparse
from dataclasses import asdict
from pathlib import Path

from archguard.domain.canonical import canonical_json
from archguard.domain.orchestration import fingerprint
from archguard.domain.phase128f import (
    ADAPTER_SCHEMA,
    BATCH_A,
    BATCH_B,
    EvaluatorAdapter,
    SandboxContract,
)

CANDIDATE_FINGERPRINT = "d1068112a12c63e24ee780ad9b31b05c04f9b1417efa50ffa04a1b8b4aac1903"
POLICY_FINGERPRINT = "0987d60ff9b5c2071f0c1dd82a91c680a6aafa885a37b12003bc34dc4add7e01"
BUGSINPY_REVISION = "11c5f1eea954a42132cfd06bf257766a7963e0fd"
SANDBOX = SandboxContract()


def _adapter(
    task_id: str,
    project: str,
    repository: str,
    buggy: str,
    fixed: str,
    python: str,
    upstream_requirements_sha256: str,
    dependency_constraints: tuple[str, ...],
    evaluator_argv: tuple[str, ...],
    selector: str,
    license_id: str,
    license_sha256: str,
    reviewed: bool = False,
    evaluator_fixture_path: str | None = None,
) -> EvaluatorAdapter:
    number = task_id.rsplit("-", 1)[1]
    return EvaluatorAdapter(
        schema=ADAPTER_SCHEMA if reviewed else "archguard.evaluator-adapter/v2",
        task_id=task_id,
        project=project,
        repository=repository,
        buggy_revision=buggy,
        fixed_revision=fixed,
        python_version=python,
        dependency_locator=f"BugsInPy@{BUGSINPY_REVISION}:projects/{project}/bugs/{number}/requirements.txt",
        upstream_requirements_sha256=upstream_requirements_sha256,
        upstream_requirements_empty=(
            upstream_requirements_sha256
            == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        ),
        dependency_constraints=dependency_constraints,
        constraint_set_fingerprint=fingerprint({"constraints": list(dependency_constraints)}),
        constraint_provenance=f"BugsInPy@{BUGSINPY_REVISION}:reviewed adapter constraints",
        evaluator_argv=evaluator_argv,
        test_selectors=(selector,),
        expected_buggy_outcome="TEST_FAILURE",
        fixed_success="EXIT_ZERO",
        source_license_id=license_id,
        source_license_sha256=license_sha256,
        sandbox=SANDBOX,
        buggy_test_selectors=(selector,) if reviewed else (),
        fixed_test_selectors=(selector,) if reviewed else (),
        evaluator_source_type=(
            "FIXED_REVISION_QUARANTINED_TEST" if reviewed else "PROJECT_REVISION"
        ),
        evaluator_provenance=(
            f"BugsInPy@{BUGSINPY_REVISION}:projects/{project}/bugs/{number}/run_test.sh"
            if reviewed
            else ""
        ),
        installation_plan=(
            ("OFFICIAL_SETUP", "PYTHONPATH_SOURCE")
            if project == "cookiecutter"
            else (
                "OFFICIAL_SETUP",
                "PYTHONPATH_SOURCE",
                "GENERATED_TEST_PACKAGE_MARKER",
                "GENERATED_VERSION_MODULE_SHIM",
            )
            if project == "black"
            else ("OFFICIAL_SETUP", "PYTHONPATH_SOURCE")
        )
        if reviewed
        else (),
        expected_framework=evaluator_argv[2] if reviewed else "",
        quarantine_policy="READ_ONLY_FIXED_TEST_NO_AGENT_ACCESS" if reviewed else "NONE",
        review_status="REVIEWED" if reviewed else "LEGACY",
        evaluator_fixture_path=evaluator_fixture_path if reviewed else None,
        evaluator_fixture_sha256={
            "PySnooper-1": "7a3d64cd702fdfa1eba8c08ac3c8934948a3ef0178f141c1f5599307c1fe59f3",
            "PySnooper-3": "852e76799d5a97d2e8e87d0db6b5e6fd7884fbff6fbe2049734c268bd8c7c753",
            "black-1": "3a690fb9c66f3d85b89594f4577e3632ec069389e3af669becb3b899ded59373",
            "black-2": "a903d77e94a0bc7d2944f1d7a27531c6305048a7617441791bb706449150d01c",
            "black-3": "bfe05145b8c4361ae744ccb71ab8780dd392ac712596c77075c779f6749fbc15",
            "black-4": "156be8f87263e7378daa2d5533334e1d9ff1a4ab291b82ecd3e3c3f3039538f2",
            "cookiecutter-4": "c74875f38e1948d6b5bb1e8ea04d165df54d188d04be14e79439b907ca266d0f",
        }.get(task_id)
        if reviewed
        else None,
        working_directory="/tmp/archguard" if project == "cookiecutter" else "/workspace",
    )


def adapters() -> tuple[EvaluatorAdapter, ...]:
    pysnooper_license = "5db83d6347f7e52946b736c71d0d59bb80c8a4485fcfa0a5140bdd839152be88"
    black_license = "9c0428f0c3b4779850cf5bd96e11aaa8afc72d4a86d4a36223d7aba2e58d6e00"
    return (
        _adapter(
            "PySnooper-1",
            "PySnooper",
            "https://github.com/cool-RR/PySnooper",
            "e21a31162f4c54be693d8ca8260e42393b39abd3",
            "56f22f8ffe1c6b2be4d2cf3ad1987fdb66113da2",
            "3.8.1",
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            ("pytest==5.4.3", "python_toolbox==1.3.2", "six==1.15.0"),
            ("python", "-m", "pytest", "-q", "-s"),
            "tests/test_chinese.py::test_chinese",
            "MIT",
            pysnooper_license,
            reviewed=True,
            evaluator_fixture_path="tests/test_chinese.py",
        ),
        _adapter(
            "PySnooper-3",
            "PySnooper",
            "https://github.com/cool-RR/PySnooper",
            "6e3d797be3fa0a746fb5b1b7c7fea78eb926c208",
            "15555ed760000b049aff8fecc79d29339c1224c3",
            "3.8.1",
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            (
                "decorator==4.4.2",
                "future==0.18.2",
                "pytest==5.4.3",
                "python_toolbox==1.3.2",
                "six==1.15.0",
            ),
            ("python", "-m", "pytest", "-q", "-s"),
            "tests/test_pysnooper.py::test_file_output",
            "MIT",
            "0c4250d2a9f0e39d024593ede44eb5044e5fbd1175a8962ec9659d8ace34de9e",
            reviewed=True,
            evaluator_fixture_path="tests/test_pysnooper.py",
        ),
        _adapter(
            "black-1",
            "black",
            "https://github.com/psf/black",
            "26c9465a22c732ab1e17b0dec578fa3432e9b558",
            "c0a7582e3d4cc8bec3b7f5a6c52b36880dcb57d7",
            "3.8.3",
            "0bf753789d959137ae76826b3df5446e232f1034921fe90c8fb1550f040e7b84",
            (
                "appdirs==1.4.3",
                "attrs==19.3.0",
                "click==7.1.1",
                "pathspec==0.7.0",
                "regex==2020.2.20",
                "toml==0.10.0",
                "typed-ast==1.4.0",
                "typing-extensions==3.7.4.2",
                "mypy-extensions==0.4.3",
            ),
            ("python", "-m", "unittest", "-q"),
            "tests.test_black.BlackTestCase.test_works_in_mono_process_only_environment",
            "MIT",
            black_license,
            reviewed=True,
            evaluator_fixture_path="tests/test_black.py",
        ),
        _adapter(
            "cookiecutter-4",
            "cookiecutter",
            "https://github.com/cookiecutter/cookiecutter",
            "9568ab6ecd2d6836646006c59473c4a4ac0dee04",
            "457a1a4e862aab4102b644ff1d2b2e2b5a766b3c",
            "3.6.9",
            "fad92c7f16302f7ac496fa06c7b87cd137bdc4fbc6dc39c0fc48e5452fc94c8e",
            (
                "arrow==0.15.6",
                "binaryornot==0.4.4",
                "click==7.1.2",
                "Jinja2==2.11.2",
                "jinja2-time==0.2.0",
                "poyo==0.5.0",
                "pytest==5.4.3",
                "python-slugify==4.0.0",
                "requests==2.23.0",
                "text-unidecode==1.3",
            ),
            ("python", "-m", "pytest", "-q", "-s"),
            "tests/test_hooks.py::TestExternalHooks::test_run_failing_hook",
            "BSD-3-Clause",
            "31f691f875aa4ccfbd491b1dc3bf0f2f44e48c53ec573c4eaae79a9afedae7cf",
            reviewed=True,
            evaluator_fixture_path="tests/test_hooks.py",
        ),
        _adapter(
            "black-2",
            "black",
            "https://github.com/psf/black",
            "c8ca6b2b9ff3510bee12129824cebfc2fc51e5b2",
            "892eddacd215d685e136686b7f629ade70adca83",
            "3.8.3",
            "9f397c088543e408d3a9611b315d6ced6e94ebbb2f8f67844ab8fa3ec19d401c",
            (
                "appdirs==1.4.3",
                "attrs==19.3.0",
                "click==7.1.1",
                "pathspec==0.7.0",
                "regex==2020.2.20",
                "toml==0.10.0",
                "typed-ast==1.4.0",
                "typing-extensions==3.7.4.2",
                "mypy-extensions==0.4.3",
            ),
            ("python", "-m", "unittest", "-q"),
            "tests.test_black.BlackTestCase.test_fmtonoff4",
            "MIT",
            black_license,
            reviewed=True,
            evaluator_fixture_path="tests/test_black.py",
        ),
        _adapter(
            "black-3",
            "black",
            "https://github.com/psf/black",
            "8126b4f6a9342290de4655e6a8a78cd288ce7daa",
            "7a14a37981862ef418f3cdb4a7e2375856f97529",
            "3.8.3",
            "884f3f07aa0060f4650fd197f63c27c7d8c0e530afdee5d93e34f533f6e5a8bb",
            (
                "appdirs==1.4.3",
                "attrs==19.3.0",
                "click==7.1.1",
                "pathspec==0.7.0",
                "regex==2020.2.20",
                "toml==0.10.0",
                "typed-ast==1.4.0",
                "typing-extensions==3.7.4.2",
                "mypy-extensions==0.4.3",
            ),
            ("python", "-m", "unittest", "-q"),
            "tests.test_black.BlackTestCase.test_invalid_config_return_code",
            "MIT",
            black_license,
            reviewed=True,
            evaluator_fixture_path="tests/test_black.py",
        ),
        _adapter(
            "black-4",
            "black",
            "https://github.com/psf/black",
            "65ea568e3301951f26e0e3b98f6d5dc80132e917",
            "c7495b9aa098ef7a358fc74556359d21c6a4ba11",
            "3.8.3",
            "2fdb8f4e1cded9c90678d86271ae3d7eb1789754217eee53403e39016b224b15",
            (
                "appdirs==1.4.3",
                "attrs==19.3.0",
                "click==7.0",
                "pathspec==0.7.0",
                "regex==2020.2.20",
                "toml==0.10.0",
                "typed-ast==1.4.0",
            ),
            ("python", "-m", "unittest", "-q"),
            "tests.test_black.BlackTestCase.test_beginning_backslash",
            "MIT",
            black_license,
            reviewed=True,
            evaluator_fixture_path="tests/test_black.py",
        ),
    )


def registry() -> dict[str, object]:
    body: dict[str, object] = {
        "schema": "archguard.evaluator-adapter-registry/v2",
        "candidate_registry_fingerprint": CANDIDATE_FINGERPRINT,
        "selection_policy_fingerprint": POLICY_FINGERPRINT,
        "bugsinpy_revision": BUGSINPY_REVISION,
        "batch_a": list(BATCH_A),
        "batch_b": list(BATCH_B),
        "imported_prior_task": "PySnooper-2",
        "adapters": [asdict(adapter) for adapter in adapters()],
        "phase_13_ready": False,
    }
    body["fingerprint"] = fingerprint(body)
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json(registry()))


if __name__ == "__main__":
    main()
