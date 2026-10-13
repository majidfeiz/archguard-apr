"""Sequential frozen Phase 13 orchestration with fail-closed cost accounting."""

from dataclasses import asdict, replace
from decimal import Decimal

from archguard.application.ports.phase13 import (
    FrozenExecutionPort,
    Phase13ArtifactPort,
    ProviderAttemptError,
    TreatmentRequest,
)
from archguard.domain.orchestration import fingerprint
from archguard.domain.phase13 import (
    FROZEN_EXECUTIONS,
    POPULATION_FINGERPRINT,
    PROVIDER_FINGERPRINT,
    CostState,
    ExecutionResult,
    TerminalClassification,
    experiment_id,
    validate_frozen_executions,
)
from archguard.domain.provider_preflight import CostGuard, ProviderExperimentConfiguration

RETRYABLE = frozenset({"connection_failure", "provider_5xx", "rate_limit", "timeout"})


class ControlledStop(RuntimeError):
    pass


def run_frozen_experiment(
    *,
    protocol_fingerprint: str,
    configuration: ProviderExperimentConfiguration,
    executor: FrozenExecutionPort,
    artifacts: Phase13ArtifactPort,
) -> tuple[ExecutionResult, ...]:
    """Execute the immutable schedule once, persisting evidence after every attempt."""
    validate_frozen_executions(FROZEN_EXECUTIONS)
    if configuration.population_fingerprint != POPULATION_FINGERPRINT:
        raise ValueError("population drift")
    if configuration.provider_configuration_fingerprint != PROVIDER_FINGERPRINT:
        raise ValueError("provider configuration drift")
    guard = CostGuard(configuration)
    state = CostState()
    artifacts.write_cost_state(asdict(state))
    completed: list[ExecutionResult] = []
    identifier = experiment_id(protocol_fingerprint)
    try:
        for identity in FROZEN_EXECUTIONS:
            if state.observed_usd + state.reserved_usd >= configuration.warning_cost_usd:
                state = replace(state, stop_reason="emergency_cost_threshold")
                artifacts.write_cost_state(asdict(state))
                break
            request = _request(identity, identifier)
            try:
                reservation = guard.authorize(
                    state.observed_usd, state.reserved_usd, state.calls_started
                )
            except ValueError as error:
                state = replace(
                    state, reserved_usd=Decimal("0"), stop_reason="cost_guard_rejection"
                )
                artifacts.write_cost_state(asdict(state))
                raise ControlledStop("cost_guard_rejection") from error
            state = replace(
                state,
                reserved_usd=reservation,
                calls_started=state.calls_started + 1,
                stop_reason="running",
            )
            artifacts.write_cost_state(asdict(state))
            try:
                result = executor.execute(request)
            except ProviderAttemptError as error:
                state = replace(state, reserved_usd=Decimal("0"), stop_reason=error.category)
                artifacts.write_cost_state(asdict(state))
                if error.category not in RETRYABLE:
                    break
                try:
                    reservation = guard.authorize(
                        state.observed_usd, state.reserved_usd, state.calls_started
                    )
                except ValueError:
                    state = replace(state, stop_reason="cost_guard_rejection")
                    artifacts.write_cost_state(asdict(state))
                    break
                state = replace(
                    state,
                    reserved_usd=reservation,
                    attempted_retries=state.attempted_retries + 1,
                    calls_started=state.calls_started + 1,
                    stop_reason="running",
                )
                artifacts.write_cost_state(asdict(state))
                try:
                    result = executor.execute(request, retry=True)
                except ProviderAttemptError as retry_error:
                    state = replace(
                        state, reserved_usd=Decimal("0"), stop_reason=retry_error.category
                    )
                    artifacts.write_cost_state(asdict(state))
                    break
                except Exception:
                    state = replace(
                        state, reserved_usd=Decimal("0"), stop_reason="execution_failure"
                    )
                    artifacts.write_cost_state(asdict(state))
                    break
            except Exception:
                state = replace(state, reserved_usd=Decimal("0"), stop_reason="execution_failure")
                artifacts.write_cost_state(asdict(state))
                break
            if result.identity != identity or result.experiment_id != identifier:
                state = replace(
                    state, reserved_usd=Decimal("0"), stop_reason="evidence_identity_failure"
                )
                artifacts.write_cost_state(asdict(state))
                break
            try:
                state = _record(state, result)
            except ValueError:
                state = replace(
                    state, reserved_usd=Decimal("0"), stop_reason="usage_schema_failure"
                )
                artifacts.write_cost_state(asdict(state))
                break
            artifacts.write_result(result)
            artifacts.write_cost_state(asdict(state))
            completed.append(result)
            if result.terminal_classification is TerminalClassification.COST_STOP:
                break
        state = replace(
            state,
            reserved_usd=Decimal("0"),
            stop_reason="complete" if len(completed) == 6 else state.stop_reason,
        )
    finally:
        cleaned = executor.cleanup()
        if not cleaned:
            state = replace(state, stop_reason="cleanup_failure")
        artifacts.write_cleanup({"schema": "archguard.phase-13-cleanup/v1", "complete": cleaned})
    artifacts.write_cost_state(asdict(state))
    artifacts.write_manifest(
        {
            "schema": "archguard.phase-13-manifest/v1",
            "experiment_id": identifier,
            "population_fingerprint": POPULATION_FINGERPRINT,
            "protocol_fingerprint": protocol_fingerprint,
            "provider_configuration_fingerprint": PROVIDER_FINGERPRINT,
            "completed_executions": len(completed),
            "attrition": 6 - len(completed),
            "total_calls": state.calls_started,
            "total_cost_usd": str(state.observed_usd),
            "stop_reason": state.stop_reason,
            "result_fingerprints": [fingerprint(item.source_free_record()) for item in completed],
        }
    )
    return tuple(completed)


def _request(identity: object, identifier: str) -> TreatmentRequest:
    from archguard.domain.phase13 import Condition, ExecutionIdentity

    if not isinstance(identity, ExecutionIdentity):
        raise TypeError("invalid identity")
    common = {"experiment_id": identifier, "identity": asdict(identity), "source_budget": "fixed"}
    return TreatmentRequest(
        identity,
        fingerprint({**common, "treatment": identity.condition.value}),
        fingerprint({**common, "manifest": "source-context-v1"}),
        identity.condition is Condition.ARCHGUARD,
    )


def _record(state: CostState, result: ExecutionResult) -> CostState:
    observed = state.observed_usd + result.observed_usd
    if observed > Decimal("4.50"):
        raise ValueError("observed cost exceeded hard ceiling")
    return CostState(
        observed,
        Decimal("0"),
        state.completed_primary + 1,
        state.attempted_retries,
        state.calls_started,
        "running",
    )
