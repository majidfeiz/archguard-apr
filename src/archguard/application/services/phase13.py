"""Sequential frozen Phase 13 orchestration with fail-closed cost accounting."""

from dataclasses import asdict, replace
from decimal import Decimal
from typing import Any

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
    checkpoint: dict[str, Any] | None = None,
) -> tuple[ExecutionResult, ...]:
    """Execute the immutable schedule once, persisting evidence after every attempt."""
    validate_frozen_executions(FROZEN_EXECUTIONS)
    if configuration.population_fingerprint != POPULATION_FINGERPRINT:
        raise ValueError("population drift")
    if configuration.provider_configuration_fingerprint != PROVIDER_FINGERPRINT:
        raise ValueError("provider configuration drift")
    guard = CostGuard(configuration)
    carried = _checkpoint_results(checkpoint, protocol_fingerprint)
    carried_calls = int(checkpoint["carried_provider_calls"]) if checkpoint else 0
    carried_cost = Decimal(str(checkpoint["carried_observed_usd"])) if checkpoint else Decimal("0")
    carried_call_ids = (
        tuple(str(item["call_id"]) for item in checkpoint["call_ledger"]) if checkpoint else ()
    )
    state = CostState(
        observed_usd=carried_cost,
        completed_primary=len(carried),
        provider_calls_started=carried_calls,
        provider_calls_completed=carried_calls,
        provider_calls_with_usage=carried_calls,
        call_ids=carried_call_ids,
    )
    artifacts.write_cost_state(asdict(state))
    completed: list[ExecutionResult] = list(carried)
    if checkpoint:
        for value in checkpoint["completed_executions"]:
            artifacts.write_imported_result(int(value["run_ordinal"]), value)
    identifier = experiment_id(protocol_fingerprint)
    schedule = FROZEN_EXECUTIONS[len(carried) :]
    try:
        for identity in schedule:
            if state.observed_usd + state.reserved_usd >= configuration.warning_cost_usd:
                state = replace(state, stop_reason="emergency_cost_threshold")
                artifacts.write_cost_state(asdict(state))
                break
            request = _request(identity, identifier)
            try:
                reservation = guard.authorize(
                    state.observed_usd, state.reserved_usd, state.provider_calls_started
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
                stop_reason="running",
            )
            artifacts.write_cost_state(asdict(state))
            try:
                result = executor.execute(request)
            except ProviderAttemptError as error:
                state = _register_call(
                    state, request.provider_call_id, completed=False, usage=False
                )
                state = replace(state, reserved_usd=Decimal("0"), stop_reason=error.category)
                artifacts.write_cost_state(asdict(state))
                if error.category not in RETRYABLE:
                    break
                try:
                    reservation = guard.authorize(
                        state.observed_usd, state.reserved_usd, state.provider_calls_started
                    )
                except ValueError:
                    state = replace(state, stop_reason="cost_guard_rejection")
                    artifacts.write_cost_state(asdict(state))
                    break
                state = replace(
                    state,
                    reserved_usd=reservation,
                    attempted_retries=state.attempted_retries + 1,
                    stop_reason="running",
                )
                artifacts.write_cost_state(asdict(state))
                request = replace(
                    request,
                    provider_call_id=fingerprint(
                        {"experiment_id": identifier, "ordinal": identity.ordinal, "attempt": 2}
                    ),
                )
                try:
                    result = executor.execute(request, retry=True)
                except ProviderAttemptError as retry_error:
                    state = _register_call(
                        state, request.provider_call_id, completed=False, usage=False
                    )
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
            result = replace(result, provider_call_id=request.provider_call_id)
            state = _register_call(state, request.provider_call_id, completed=True, usage=True)
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
    if state.observed_usd != sum((item.observed_usd for item in completed), Decimal("0")):
        raise ValueError("aggregate observed cost mismatch")
    if state.provider_calls_with_usage < len(completed):
        raise ValueError("provider call ledger is incomplete")
    artifacts.write_manifest(
        {
            "schema": "archguard.phase-13-manifest/v1",
            "experiment_id": identifier,
            "population_fingerprint": POPULATION_FINGERPRINT,
            "protocol_fingerprint": protocol_fingerprint,
            "provider_configuration_fingerprint": PROVIDER_FINGERPRINT,
            "carried_executions": len(carried),
            "newly_completed_executions": len(completed) - len(carried),
            "completed_executions": len(completed),
            "attrition": 6 - len(completed),
            "carried_provider_calls": carried_calls,
            "new_provider_calls": state.provider_calls_started - carried_calls,
            "provider_calls_started": state.provider_calls_started,
            "provider_calls_completed": state.provider_calls_completed,
            "provider_calls_with_usage": state.provider_calls_with_usage,
            "call_ledger": list(state.call_ids),
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
        fingerprint({"experiment_id": identifier, "ordinal": identity.ordinal, "attempt": 1}),
    )


def _record(state: CostState, result: ExecutionResult) -> CostState:
    observed = state.observed_usd + result.observed_usd
    if observed > Decimal("4.50"):
        raise ValueError("observed cost exceeded hard ceiling")
    if state.provider_calls_with_usage < state.completed_primary + 1:
        raise ValueError("execution has no provider call with usage")
    return CostState(
        observed_usd=observed,
        reserved_usd=Decimal("0"),
        completed_primary=state.completed_primary + 1,
        attempted_retries=state.attempted_retries,
        provider_calls_started=state.provider_calls_started,
        provider_calls_completed=state.provider_calls_completed,
        provider_calls_with_usage=state.provider_calls_with_usage,
        call_ids=state.call_ids,
        stop_reason="running",
    )


def _register_call(state: CostState, call_id: str, *, completed: bool, usage: bool) -> CostState:
    if call_id in state.call_ids:
        raise ValueError("duplicate provider call identity")
    return replace(
        state,
        provider_calls_started=state.provider_calls_started + 1,
        provider_calls_completed=state.provider_calls_completed + int(completed),
        provider_calls_with_usage=state.provider_calls_with_usage + int(usage),
        call_ids=(*state.call_ids, call_id),
    )


def _checkpoint_results(
    checkpoint: dict[str, Any] | None, protocol_fingerprint: str
) -> tuple[ExecutionResult, ...]:
    if checkpoint is None:
        return ()
    if checkpoint.get("protocol_fingerprint") != protocol_fingerprint:
        raise ValueError("checkpoint protocol drift")
    ordinals = checkpoint.get("completed_ordinals")
    if not isinstance(ordinals, list) or ordinals != list(range(1, len(ordinals) + 1)):
        raise ValueError("checkpoint executions are not an exact prefix")
    raw = checkpoint.get("completed_executions")
    if not isinstance(raw, list) or len(raw) != len(ordinals):
        raise ValueError("checkpoint execution mismatch")
    results = tuple(_result_from_record(item) for item in raw)
    if tuple(item.identity for item in results) != FROZEN_EXECUTIONS[: len(results)]:
        raise ValueError("checkpoint execution identity drift")
    return results


def _result_from_record(value: object) -> ExecutionResult:
    from archguard.domain.phase13 import Condition, ExecutionIdentity, ProviderUsage

    if not isinstance(value, dict):
        raise ValueError("invalid checkpoint execution")
    identity = ExecutionIdentity(
        int(value["run_ordinal"]),
        str(value["task_id"]),
        str(value["project"]),
        Condition(value["condition"]),
    )
    usage = ProviderUsage(**value["usage"])
    return ExecutionResult(
        experiment_id=str(value["experiment_id"]),
        identity=identity,
        immutable_buggy_revision=str(value["immutable_buggy_revision"]),
        protocol_fingerprint=str(value["protocol_fingerprint"]),
        request_fingerprint=str(value["request_fingerprint"]),
        context_manifest_fingerprint=str(value["context_manifest_fingerprint"]),
        response_fingerprint=str(value["response_fingerprint"]),
        patch_fingerprint=str(value["patch_fingerprint"]),
        patch_parsed=bool(value["patch_parsed"]),
        patch_applied=bool(value["patch_applied"]),
        files_changed=int(value["files_changed"]),
        lines_added=int(value["lines_added"]),
        lines_deleted=int(value["lines_deleted"]),
        unsafe_patch_rejection=value["unsafe_patch_rejection"],
        architecture_status=str(value["architecture_status"]),
        architecture_violations=tuple(tuple(item) for item in value["architecture_violations"]),
        evaluator_executed=bool(value["evaluator_executed"]),
        buggy_failure_reproduced=bool(value["buggy_failure_reproduced"]),
        candidate_test_outcome=str(value["candidate_test_outcome"]),
        tests_fixed=int(value["tests_fixed"]),
        regressions=int(value["regressions"]),
        repair_success=bool(value["repair_success"]),
        terminal_classification=TerminalClassification(value["terminal_classification"]),
        usage=usage,
        observed_usd=Decimal(str(value["observed_usd"])),
        attempt_count=int(value["attempt_count"]),
        duration_bucket=str(value["duration_bucket"]),
        cleanup_status=str(value["cleanup_status"]),
    )
