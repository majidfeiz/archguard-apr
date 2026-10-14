import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from archguard.application.ports.phase13 import ProviderAttemptError, TreatmentRequest
from archguard.application.services.phase13 import run_frozen_experiment
from archguard.domain.phase13 import (
    FROZEN_EXECUTIONS,
    POPULATION_FINGERPRINT,
    ExecutionResult,
    ProviderUsage,
    TerminalClassification,
    experiment_id,
)
from archguard.infrastructure.phase13_artifacts import (
    SourceFreeArtifacts,
    validate_artifact_directory,
)
from archguard.infrastructure.phase13_protocol import load_phase13_protocol, validate_amendment
from archguard.infrastructure.provider_preflight import load_phase13_provider_configuration


class FakeExecutor:
    def __init__(self, protocol: str) -> None:
        self.protocol = protocol
        self.requests: list[TreatmentRequest] = []

    def execute(self, request: TreatmentRequest, *, retry: bool = False) -> ExecutionResult:
        self.requests.append(request)
        return ExecutionResult(
            experiment_id(self.protocol),
            request.identity,
            "a" * 40,
            self.protocol,
            request.request_fingerprint,
            request.context_manifest_fingerprint,
            "b" * 64,
            "c" * 64,
            True,
            True,
            1,
            1,
            0,
            None,
            "skipped" if request.identity.condition.value == "baseline" else "passed",
            (),
            True,
            True,
            "passed",
            1,
            0,
            True,
            TerminalClassification.SUCCESS,
            ProviderUsage(10, 0, 10, 2),
            Decimal("0.0002"),
            1,
            "under_1_minute",
            "complete",
        )

    def cleanup(self) -> bool:
        return True


class RetryExecutor(FakeExecutor):
    def __init__(self, protocol: str, category: str) -> None:
        super().__init__(protocol)
        self.category = category
        self.attempts = 0

    def execute(self, request: TreatmentRequest, *, retry: bool = False) -> ExecutionResult:
        self.attempts += 1
        if self.attempts == 1:
            raise ProviderAttemptError(self.category)
        return super().execute(request, retry=retry)


def _protocol(repository_root: Path) -> dict[str, Any]:
    return load_phase13_protocol(
        repository_root / "research/protocol/exploratory-feasibility-v2.json"
    )


def test_historical_protocol_is_preserved(repository_root: Path) -> None:
    old = json.loads(
        (repository_root / "research/protocol/exploratory-feasibility-v1.json").read_text()
    )
    assert old["fingerprint"] == "93494690f402d17e511d9cad1fdc92907d408ae3a923139d30537894f9ab8ce7"
    assert old["definition"]["run_count"]["repetitions_per_task_condition"] == 3


def test_amended_protocol_freezes_exact_six(repository_root: Path) -> None:
    protocol = _protocol(repository_root)
    assert protocol["repetitions_per_task_condition"] == 1
    assert protocol["primary_executions"] == 6
    assert protocol["provider"]["maximum_calls"] == 12
    assert protocol["provider"]["status"] == "CONFIGURED"
    assert protocol["population_fingerprint"] == POPULATION_FINGERPRINT
    assert [(item["task_id"], item["condition"]) for item in protocol["execution_order"]] == [
        (item.task_id, item.condition.value) for item in FROZEN_EXECUTIONS
    ]


def test_amendment_is_prospective(repository_root: Path) -> None:
    protocol = _protocol(repository_root)
    amendment = validate_amendment(
        repository_root / "research/reviews/phase-13-six-run-protocol-amendment.json", protocol
    )
    assert amendment["provider_calls_at_decision"] == 0
    assert amendment["observed_scientific_outcomes"] == 0
    assert amendment["observed_provider_cost_usd"] == "0"


def test_interpretation_remains_descriptive(repository_root: Path) -> None:
    interpretation = _protocol(repository_root)["interpretation"]
    assert interpretation == {
        "confirmatory_hypothesis_acceptance": False,
        "descriptive_only": True,
        "generalization": "frozen_three_task_population_only",
        "statistical_superiority_claim": False,
        "study_type": "EXPLORATORY_FEASIBILITY",
    }


def test_protocol_drift_fails_closed(repository_root: Path, tmp_path: Path) -> None:
    value = _protocol(repository_root)
    value["primary_executions"] = 7
    target = tmp_path / "protocol.json"
    target.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(ValueError):
        load_phase13_protocol(target)


def test_fake_runner_is_sequential_and_treatment_isolated(
    repository_root: Path, tmp_path: Path
) -> None:
    protocol = _protocol(repository_root)
    configuration = load_phase13_provider_configuration(
        repository_root / "configs/experiments/phase13-provider.json"
    )
    executor = FakeExecutor(protocol["fingerprint"])
    artifacts = SourceFreeArtifacts(tmp_path / "evidence")
    results = run_frozen_experiment(
        protocol_fingerprint=protocol["fingerprint"],
        configuration=configuration,
        executor=executor,
        artifacts=artifacts,
    )
    assert tuple(item.identity for item in results) == FROZEN_EXECUTIONS
    assert [item.architecture_treatment for item in executor.requests] == [False, True] * 3
    assert len(executor.requests) == 6
    validate_artifact_directory(tmp_path / "evidence")


def test_no_seventh_execution_can_be_scheduled(repository_root: Path, tmp_path: Path) -> None:
    protocol = _protocol(repository_root)
    configuration = load_phase13_provider_configuration(
        repository_root / "configs/experiments/phase13-provider.json"
    )
    executor = FakeExecutor(protocol["fingerprint"])
    run_frozen_experiment(
        protocol_fingerprint=protocol["fingerprint"],
        configuration=configuration,
        executor=executor,
        artifacts=SourceFreeArtifacts(tmp_path / "evidence"),
    )
    assert len(executor.requests) == 6


def test_artifact_allowlist_and_leakage_rejection(tmp_path: Path) -> None:
    artifacts = SourceFreeArtifacts(tmp_path / "evidence")
    with pytest.raises(ValueError):
        artifacts._write("raw-response.json", {"response": "secret"})
    with pytest.raises(ValueError):
        artifacts._write("manifest.json", {"prompt": "source"})


def test_configuration_drift_fails_before_executor(repository_root: Path, tmp_path: Path) -> None:
    protocol = _protocol(repository_root)
    configuration = load_phase13_provider_configuration(
        repository_root / "configs/experiments/phase13-provider.json"
    )
    executor = FakeExecutor(protocol["fingerprint"])
    with pytest.raises(ValueError):
        run_frozen_experiment(
            protocol_fingerprint=protocol["fingerprint"],
            configuration=replace(
                configuration,
                population_fingerprint="0" * 64,
                provider_configuration_fingerprint="",
            ),
            executor=executor,
            artifacts=SourceFreeArtifacts(tmp_path / "evidence"),
        )
    assert executor.requests == []


@pytest.mark.parametrize(
    "category", ["timeout", "connection_failure", "rate_limit", "provider_5xx"]
)
def test_retry_policy_allows_one_network_retry(
    repository_root: Path, tmp_path: Path, category: str
) -> None:
    protocol = _protocol(repository_root)
    configuration = load_phase13_provider_configuration(
        repository_root / "configs/experiments/phase13-provider.json"
    )
    executor = RetryExecutor(protocol["fingerprint"], category)
    results = run_frozen_experiment(
        protocol_fingerprint=protocol["fingerprint"],
        configuration=configuration,
        executor=executor,
        artifacts=SourceFreeArtifacts(tmp_path / "evidence"),
    )
    assert len(results) == 6
    assert executor.attempts == 7
    state = json.loads((tmp_path / "evidence/cost-state.json").read_text())
    assert state["attempted_retries"] == 1
    assert state["provider_calls_started"] == 7
    assert state["provider_calls_completed"] == 6
    assert state["provider_calls_with_usage"] == 6


@pytest.mark.parametrize(
    "category", ["authentication_failure", "billing_failure", "quota_failure", "invalid_patch"]
)
def test_non_network_failures_are_not_retried(
    repository_root: Path, tmp_path: Path, category: str
) -> None:
    protocol = _protocol(repository_root)
    configuration = load_phase13_provider_configuration(
        repository_root / "configs/experiments/phase13-provider.json"
    )
    executor = RetryExecutor(protocol["fingerprint"], category)
    results = run_frozen_experiment(
        protocol_fingerprint=protocol["fingerprint"],
        configuration=configuration,
        executor=executor,
        artifacts=SourceFreeArtifacts(tmp_path / "evidence"),
    )
    assert results == ()
    assert executor.attempts == 1


def test_fake_runs_are_byte_identical(repository_root: Path, tmp_path: Path) -> None:
    protocol = _protocol(repository_root)
    configuration = load_phase13_provider_configuration(
        repository_root / "configs/experiments/phase13-provider.json"
    )
    roots = [tmp_path / "first", tmp_path / "second"]
    for root in roots:
        run_frozen_experiment(
            protocol_fingerprint=protocol["fingerprint"],
            configuration=configuration,
            executor=FakeExecutor(protocol["fingerprint"]),
            artifacts=SourceFreeArtifacts(root),
        )
    first = {path.name: path.read_bytes() for path in roots[0].iterdir()}
    second = {path.name: path.read_bytes() for path in roots[1].iterdir()}
    assert first == second


def test_workflow_scopes_secret_to_live_step(repository_root: Path) -> None:
    source = (repository_root / ".github/workflows/phase-13-experiment.yml").read_text()
    assert source.count("OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}") == 1
    assert "--allow-missing-secret" in source
    assert "Scientific execution remains intentionally unavailable" not in source
    assert "experiment run-frozen" in source
    assert "execute_scientific_run:\n" in source
    assert "default: false" in source
    assert "if: inputs.execute_scientific_run" in source
    assert "RUN_FROZEN_PHASE_13" in source
    assert '.historical_stop_reason == "pre_provider_failure"' in source
    assert '.historical_stop_reason == "execution_failure"' not in source


class AlwaysFailExecutor(FakeExecutor):
    def __init__(self, protocol: str, failures: list[Exception]) -> None:
        super().__init__(protocol)
        self.failures = failures

    def execute(self, request: TreatmentRequest, *, retry: bool = False) -> ExecutionResult:
        self.requests.append(request)
        raise self.failures.pop(0)


def test_retry_failure_is_recorded_and_stops(repository_root: Path, tmp_path: Path) -> None:
    protocol = _protocol(repository_root)
    configuration = load_phase13_provider_configuration(
        repository_root / "configs/experiments/phase13-provider.json"
    )
    executor = AlwaysFailExecutor(
        protocol["fingerprint"],
        [ProviderAttemptError("timeout"), ProviderAttemptError("provider_5xx")],
    )
    results = run_frozen_experiment(
        protocol_fingerprint=protocol["fingerprint"],
        configuration=configuration,
        executor=executor,
        artifacts=SourceFreeArtifacts(tmp_path / "evidence"),
    )
    assert results == ()
    assert len(executor.requests) == 2
    state = json.loads((tmp_path / "evidence/cost-state.json").read_text())
    assert state["stop_reason"] == "provider_5xx"


def test_unexpected_execution_failure_is_recorded(repository_root: Path, tmp_path: Path) -> None:
    protocol = _protocol(repository_root)
    configuration = load_phase13_provider_configuration(
        repository_root / "configs/experiments/phase13-provider.json"
    )
    executor = AlwaysFailExecutor(protocol["fingerprint"], [RuntimeError("local")])
    results = run_frozen_experiment(
        protocol_fingerprint=protocol["fingerprint"],
        configuration=configuration,
        executor=executor,
        artifacts=SourceFreeArtifacts(tmp_path / "evidence"),
    )
    assert results == ()
    state = json.loads((tmp_path / "evidence/cost-state.json").read_text())
    assert state["stop_reason"] == "execution_failure"
    assert state["provider_calls_started"] == 0


@pytest.mark.parametrize(
    "classification",
    [
        TerminalClassification.INVALID_PATCH,
        TerminalClassification.UNSAFE_PATCH,
        TerminalClassification.PATCH_APPLICATION_FAILED,
        TerminalClassification.ARCHITECTURE_VIOLATION,
        TerminalClassification.EVALUATOR_FAILURE,
        TerminalClassification.TESTS_FAILED,
        TerminalClassification.REPAIR_UNSUCCESSFUL,
        TerminalClassification.SUCCESS,
    ],
)
def test_terminal_scientific_outcomes_continue_to_next_ordinal(
    repository_root: Path,
    tmp_path: Path,
    classification: TerminalClassification,
) -> None:
    protocol = _protocol(repository_root)
    configuration = load_phase13_provider_configuration(
        repository_root / "configs/experiments/phase13-provider.json"
    )

    class ScientificOutcomeExecutor(FakeExecutor):
        def execute(self, request: TreatmentRequest, *, retry: bool = False) -> ExecutionResult:
            result = super().execute(request, retry=retry)
            return replace(result, terminal_classification=classification)

    executor = ScientificOutcomeExecutor(protocol["fingerprint"])
    results = run_frozen_experiment(
        protocol_fingerprint=protocol["fingerprint"],
        configuration=configuration,
        executor=executor,
        artifacts=SourceFreeArtifacts(tmp_path / "evidence"),
    )
    assert len(results) == 6
    assert [request.identity.ordinal for request in executor.requests] == [1, 2, 3, 4, 5, 6]


def test_retry_unexpected_failure_is_recorded(repository_root: Path, tmp_path: Path) -> None:
    protocol = _protocol(repository_root)
    configuration = load_phase13_provider_configuration(
        repository_root / "configs/experiments/phase13-provider.json"
    )
    executor = AlwaysFailExecutor(
        protocol["fingerprint"], [ProviderAttemptError("timeout"), RuntimeError("local")]
    )
    run_frozen_experiment(
        protocol_fingerprint=protocol["fingerprint"],
        configuration=configuration,
        executor=executor,
        artifacts=SourceFreeArtifacts(tmp_path / "evidence"),
    )
    state = json.loads((tmp_path / "evidence/cost-state.json").read_text())
    assert state["stop_reason"] == "execution_failure"


def test_evidence_identity_failure_stops_before_persistence(
    repository_root: Path, tmp_path: Path
) -> None:
    protocol = _protocol(repository_root)
    configuration = load_phase13_provider_configuration(
        repository_root / "configs/experiments/phase13-provider.json"
    )

    class WrongIdentityExecutor(FakeExecutor):
        def execute(self, request: TreatmentRequest, *, retry: bool = False) -> ExecutionResult:
            result = super().execute(request, retry=retry)
            return replace(result, identity=FROZEN_EXECUTIONS[1])

    results = run_frozen_experiment(
        protocol_fingerprint=protocol["fingerprint"],
        configuration=configuration,
        executor=WrongIdentityExecutor(protocol["fingerprint"]),
        artifacts=SourceFreeArtifacts(tmp_path / "evidence"),
    )
    assert results == ()
    state = json.loads((tmp_path / "evidence/cost-state.json").read_text())
    assert state["stop_reason"] == "evidence_identity_failure"


def test_over_ceiling_result_fails_closed(repository_root: Path, tmp_path: Path) -> None:
    protocol = _protocol(repository_root)
    configuration = load_phase13_provider_configuration(
        repository_root / "configs/experiments/phase13-provider.json"
    )

    class ExpensiveExecutor(FakeExecutor):
        def execute(self, request: TreatmentRequest, *, retry: bool = False) -> ExecutionResult:
            return replace(super().execute(request, retry=retry), observed_usd=Decimal("4.51"))

    results = run_frozen_experiment(
        protocol_fingerprint=protocol["fingerprint"],
        configuration=configuration,
        executor=ExpensiveExecutor(protocol["fingerprint"]),
        artifacts=SourceFreeArtifacts(tmp_path / "evidence"),
    )
    assert results == ()
    state = json.loads((tmp_path / "evidence/cost-state.json").read_text())
    assert state["stop_reason"] == "usage_schema_failure"
