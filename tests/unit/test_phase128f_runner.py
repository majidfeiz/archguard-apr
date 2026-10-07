import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts import phase128f_runner as runner
from scripts.phase128f_registry import adapters
from scripts.phase128f_security_scan import scan


def test_structured_evaluator_argv_and_selector_are_separate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 1, b"1 failed", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    adapter = adapters()[0]
    runner._execute(adapter, "image", tmp_path, "attempt")
    command = calls[0]
    marker = command.index("evaluator")
    assert command[marker + 1 :] == [
        "python",
        "-m",
        "pytest",
        "-q",
        "-s",
        "tests/test_chinese.py::test_chinese",
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
    monkeypatch.setattr(runner, "_safe_checkout", lambda *args: None)
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
