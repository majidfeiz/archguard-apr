import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from archguard.application.ports.phase13 import ProviderAttemptError, TreatmentRequest
from archguard.domain.phase13 import (
    FROZEN_EXECUTIONS,
    MODEL,
    ProviderUsage,
    TerminalClassification,
)
from archguard.infrastructure.phase13_live import Phase13LiveExecutor, _duration_bucket
from archguard.infrastructure.provider_preflight import load_phase13_provider_configuration


def _executor(repository_root: Path, tmp_path: Path) -> Phase13LiveExecutor:
    executor = object.__new__(Phase13LiveExecutor)
    executor.repository_root = repository_root
    executor.configuration = load_phase13_provider_configuration(
        repository_root / "configs/experiments/phase13-provider.json"
    )
    executor.protocol_fingerprint = (
        "eae1920ce71c025d2d94096798daf8b14df098249743631efe9a0aa7a541fbe8"
    )
    executor.root = tmp_path / "owned"
    executor.root.mkdir()
    executor._owned = []
    return executor


def _request(ordinal: int = 1) -> TreatmentRequest:
    return TreatmentRequest(FROZEN_EXECUTIONS[ordinal - 1], "a" * 64, "b" * 64, ordinal % 2 == 0)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "under_1_minute"),
        (60, "1_to_5_minutes"),
        (300, "5_to_20_minutes"),
        (1200, "20_minutes_or_more"),
    ],
)
def test_duration_buckets(seconds: float, expected: str) -> None:
    assert _duration_bucket(seconds) == expected


def test_live_executor_requires_native_linux(
    repository_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "archguard.infrastructure.phase13_live.os.uname",
        lambda: SimpleNamespace(sysname="Darwin", machine="arm64"),
    )
    with pytest.raises(ValueError, match="native Linux"):
        Phase13LiveExecutor(repository_root, Path("provider.json"), "a" * 64)


def test_live_executor_initializes_owned_root(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owned = tmp_path / "owned-init"
    owned.mkdir()
    monkeypatch.setattr(
        "archguard.infrastructure.phase13_live.os.uname",
        lambda: SimpleNamespace(sysname="Linux", machine="x86_64"),
    )
    monkeypatch.setattr(
        "archguard.infrastructure.phase13_live.tempfile.mkdtemp", lambda **kwargs: str(owned)
    )
    executor = Phase13LiveExecutor(
        repository_root,
        repository_root / "configs/experiments/phase13-provider.json",
        "a" * 64,
    )
    assert executor.root == owned
    assert executor.repository_root == repository_root.resolve()


def test_context_excludes_tests_and_adds_treatment(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = _executor(repository_root, tmp_path)
    source = tmp_path / "source"
    (source / "pkg").mkdir(parents=True)
    (source / "tests").mkdir()
    (source / "pkg/module.py").write_text("VALUE = 1\n")
    (source / "tests/test_hidden.py").write_text("SECRET = 2\n")
    monkeypatch.setattr(executor, "_architecture_context", lambda request, root: "GRAPH")
    baseline, baseline_fingerprint = executor._context(_request(1), source)
    treated, treated_fingerprint = executor._context(_request(2), source)
    assert "VALUE = 1" in baseline
    assert "SECRET" not in baseline
    assert "ARCHITECTURE TREATMENT" not in baseline
    assert "GRAPH" in treated
    assert baseline_fingerprint == treated_fingerprint


def test_architecture_context_uses_source_free_outputs(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = _executor(repository_root, tmp_path)
    source = tmp_path / "source"
    source.mkdir()

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        if "analyze" in command:
            Path(command[-1]).write_text("{}")
        elif "build" in command:
            Path(command[-1]).write_text(
                json.dumps({"graph_fingerprint": "f", "nodes": ["n"], "edges": []})
            )
        elif "compile" in command:
            Path(command[-1]).write_text(json.dumps({"profile": "p"}))
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr("archguard.infrastructure.phase13_live.subprocess.run", fake_run)
    pysnooper = json.loads(executor._architecture_context(_request(2), source))
    black_source = tmp_path / "black" / "source"
    black_source.mkdir(parents=True)
    black = json.loads(executor._architecture_context(_request(6), black_source))
    assert pysnooper["profile"] == {"profile": "p"}
    assert black["profile"] == {"applicability": "no_frozen_project_profile"}
    assert pysnooper["nodes"] == ["n"]


def test_checkout_validates_revision_and_tree(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = _executor(repository_root, tmp_path)
    responses = iter(
        [
            "",
            "",
            "e21a31162f4c54be693d8ca8260e42393b39abd3\n",
            "100644 blob x\tfile.py\n",
        ]
    )

    def fake_run(*args: Any, **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(stdout=next(responses), returncode=0)

    monkeypatch.setattr("archguard.infrastructure.phase13_live.subprocess.run", fake_run)
    executor._checkout(_request(), tmp_path / "checkout")


@pytest.mark.parametrize(
    ("head", "modes", "message"),
    [
        ("0" * 40, "100644 blob x\tf.py", "revision"),
        (
            "e21a31162f4c54be693d8ca8260e42393b39abd3",
            "120000 blob x\tlink",
            "symlink",
        ),
    ],
)
def test_checkout_rejects_untrusted_tree(
    repository_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    head: str,
    modes: str,
    message: str,
) -> None:
    executor = _executor(repository_root, tmp_path)
    responses = iter(["", "", head, modes])
    monkeypatch.setattr(
        "archguard.infrastructure.phase13_live.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout=next(responses), returncode=0),
    )
    with pytest.raises(ValueError, match=message):
        executor._checkout(_request(), tmp_path / "checkout")


def test_git_apply_checks_before_applying(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[Any] = []

    def fake_run(*args: Any, **kwargs: Any) -> SimpleNamespace:
        calls.append(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("archguard.infrastructure.phase13_live.subprocess.run", fake_run)
    Phase13LiveExecutor._git_apply(tmp_path, b"patch")
    assert len(calls) == 2
    monkeypatch.setattr(
        "archguard.infrastructure.phase13_live.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1),
    )
    with pytest.raises(ValueError, match="rejected"):
        Phase13LiveExecutor._git_apply(tmp_path, b"patch")


def _install_openai(
    monkeypatch: pytest.MonkeyPatch,
    response: Any = None,
    error: Exception | None = None,
) -> None:
    class Responses:
        def create(self, **kwargs: Any) -> Any:
            if error is not None:
                raise error
            return response

    class OpenAI:
        def __init__(self, **kwargs: Any) -> None:
            self.responses = Responses()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=OpenAI))


def _response(**overrides: Any) -> SimpleNamespace:
    usage = SimpleNamespace(
        input_tokens=10,
        output_tokens=5,
        input_tokens_details=SimpleNamespace(cached_tokens=2),
        output_tokens_details=SimpleNamespace(reasoning_tokens=1),
    )
    values = {"model": MODEL, "output_text": json.dumps({"patch": "diff"}), "usage": usage}
    values.update(overrides)
    return SimpleNamespace(**values)


def test_invoke_validates_response_and_usage(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = _executor(repository_root, tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    _install_openai(monkeypatch, _response())
    patch, fingerprint, usage = executor._invoke(_request(), "context")
    assert patch == "diff"
    assert len(fingerprint) == 64
    assert usage == ProviderUsage(10, 2, 5, 1)


@pytest.mark.parametrize(
    ("response", "category"),
    [
        (_response(model="wrong"), "model_identity_failure"),
        (_response(usage=None), "usage_schema_failure"),
        (_response(output_text="{"), "invalid_patch_response"),
        (_response(output_text=json.dumps({"other": "x"})), "invalid_patch_response"),
        (
            _response(usage=SimpleNamespace(input_tokens="bad", output_tokens=1)),
            "usage_schema_failure",
        ),
        (
            _response(usage=SimpleNamespace(input_tokens=999999, output_tokens=1)),
            "usage_schema_failure",
        ),
    ],
)
def test_invoke_rejects_invalid_responses(
    repository_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    response: Any,
    category: str,
) -> None:
    executor = _executor(repository_root, tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    _install_openai(monkeypatch, response)
    with pytest.raises(ProviderAttemptError) as caught:
        executor._invoke(_request(), "context")
    assert caught.value.category == category


@pytest.mark.parametrize(
    ("error", "category"),
    [
        (TimeoutError(), "timeout"),
        (ConnectionError(), "connection_failure"),
        (SimpleNamespace(status_code=429, code="rate_limit"), "rate_limit"),
        (SimpleNamespace(status_code=429, code="insufficient_quota"), "quota_failure"),
        (SimpleNamespace(status_code=503, code=""), "provider_5xx"),
        (SimpleNamespace(status_code=401, code=""), "authentication_failure"),
        (SimpleNamespace(status_code=402, code=""), "quota_failure"),
    ],
)
def test_invoke_classifies_provider_failures(
    repository_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Any,
    category: str,
) -> None:
    executor = _executor(repository_root, tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    exception = (
        error
        if isinstance(error, Exception)
        else type("ProviderError", (Exception,), dict(vars(error)))()
    )
    _install_openai(monkeypatch, error=exception)
    with pytest.raises(ProviderAttemptError) as caught:
        executor._invoke(_request(), "context")
    assert caught.value.category == category


def test_cleanup_removes_owned_resources(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = _executor(repository_root, tmp_path)
    outputs = iter(["container\n", "image\n", "", ""])
    monkeypatch.setattr(
        "archguard.infrastructure.phase13_live.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout=next(outputs, ""), returncode=0),
    )
    assert executor.cleanup()


def test_cost_uses_frozen_prices(repository_root: Path, tmp_path: Path) -> None:
    executor = _executor(repository_root, tmp_path)
    assert executor._cost(ProviderUsage(10, 2, 5, 1)) > 0


def test_evaluator_runs_behind_process_boundary(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = _executor(repository_root, tmp_path)
    commands: list[list[str]] = []
    payload = {
        "architecture_status": "passed",
        "architecture_violations": [["error", 0]],
        "evaluator_executed": True,
        "buggy_failure_reproduced": True,
        "candidate_test_outcome": "passed",
        "tests_fixed": 1,
        "regressions": 0,
        "repair_success": True,
        "classification": "success",
    }

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        commands.append(command)
        return SimpleNamespace(stdout=json.dumps(payload), returncode=0)

    monkeypatch.setattr("archguard.infrastructure.phase13_live.subprocess.run", fake_run)
    result = executor._evaluate(_request(2), tmp_path / "buggy", tmp_path / "candidate")
    assert result["classification"] is TerminalClassification.SUCCESS
    assert result["architecture_violations"] == (("error", 0),)
    assert "--architecture-treatment" in commands[0]
    assert "scripts/phase13_candidate_evaluator.py" in commands[0][3]


def test_execute_returns_source_free_success(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = _executor(repository_root, tmp_path)
    patch = (
        "diff --git a/module.py b/module.py\n"
        "--- a/module.py\n"
        "+++ b/module.py\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )

    def checkout(request: TreatmentRequest, destination: Path) -> None:
        destination.mkdir(parents=True)

    evaluation = {
        "architecture_status": "passed",
        "architecture_violations": (),
        "evaluator_executed": True,
        "buggy_failure_reproduced": True,
        "candidate_test_outcome": "passed",
        "tests_fixed": 1,
        "regressions": 0,
        "repair_success": True,
        "classification": TerminalClassification.SUCCESS,
    }
    monkeypatch.setattr(executor, "_checkout", checkout)
    monkeypatch.setattr(executor, "_context", lambda request, source: ("context", "c" * 64))
    monkeypatch.setattr(
        executor,
        "_invoke",
        lambda request, context: (patch, "d" * 64, ProviderUsage(10, 2, 5, 1)),
    )
    monkeypatch.setattr(executor, "_git_apply", lambda source, value: None)
    monkeypatch.setattr(executor, "_evaluate", lambda request, buggy, candidate: evaluation)
    monkeypatch.setattr(
        "archguard.infrastructure.phase13_live.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout="", returncode=0),
    )
    result = executor.execute(_request(2), retry=True)
    assert result.patch_parsed
    assert result.patch_applied
    assert result.files_changed == 1
    assert result.lines_added == result.lines_deleted == 1
    assert result.terminal_classification is TerminalClassification.SUCCESS
    assert result.attempt_count == 2


def test_execute_rejects_malformed_patch_without_evaluator(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = _executor(repository_root, tmp_path)
    monkeypatch.setattr(
        executor,
        "_checkout",
        lambda request, destination: destination.mkdir(parents=True),
    )
    monkeypatch.setattr(executor, "_context", lambda request, source: ("context", "b" * 64))
    monkeypatch.setattr(
        executor,
        "_invoke",
        lambda request, context: ("not a diff", "d" * 64, ProviderUsage(1, 0, 1, 0)),
    )
    result = executor.execute(_request())
    assert not result.patch_parsed
    assert not result.patch_applied
    assert result.unsafe_patch_rejection == "patch_policy_rejection"
    assert result.terminal_classification is TerminalClassification.INVALID_PATCH
