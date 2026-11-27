"""Sequential, zero-retry orchestration for the frozen V2.2 call plan."""

from __future__ import annotations

from decimal import Decimal

from archguard.application.ports.v2_execution import (
    CandidateProcessor,
    CheckpointStore,
    Cleanup,
    Provider,
    ProviderAdmissionFailure,
    ProviderChargedFailure,
    RequestPreparer,
)
from archguard.domain.v2_execution import (
    BudgetLedger,
    ExecutionResult,
    ExecutionStatus,
    ProviderFailureRecord,
    frozen_identities,
)


class V2MicroPilotRunner:
    def __init__(
        self,
        preparer: RequestPreparer,
        provider: Provider,
        processor: CandidateProcessor,
        checkpoints: CheckpointStore,
        cleanup: Cleanup,
    ) -> None:
        self.preparer = preparer
        self.provider = provider
        self.processor = processor
        self.checkpoints = checkpoints
        self.cleanup_adapter = cleanup

    def run(
        self,
        ledger: BudgetLedger | None = None,
        carried: tuple[ExecutionResult, ...] = (),
        failures: tuple[ProviderFailureRecord, ...] = (),
    ) -> tuple[
        BudgetLedger,
        tuple[ExecutionResult, ...],
        tuple[ProviderFailureRecord, ...],
        bool,
    ]:
        ledger = ledger or BudgetLedger()
        if tuple(item.identity.ordinal for item in carried) != ledger.completed_ordinals:
            raise ValueError("checkpoint results contradict ledger")
        if tuple(item.identity.ordinal for item in failures) != ledger.failed_attempt_ordinals:
            raise ValueError("checkpoint failures contradict ledger")
        results = list(carried)
        recorded_failures = list(failures)
        self.checkpoints.write(ledger, tuple(results), tuple(recorded_failures))
        cleaned = False
        try:
            for identity in frozen_identities()[ledger.completed_calls :]:
                # Preparation happens before reservation, so it can never count as a provider call.
                request = self.preparer.prepare(identity)
                ledger = ledger.reserve(identity.ordinal)
                try:
                    outcome = self.provider.invoke(request)
                except ProviderAdmissionFailure as error:
                    ledger = ledger.record_provider_failure(identity.ordinal, None)
                    recorded_failures.append(
                        ProviderFailureRecord(
                            identity,
                            error.diagnostic,
                            0,
                            0,
                            0,
                            Decimal("0"),
                        )
                    )
                    self.checkpoints.write(ledger, tuple(results), tuple(recorded_failures))
                    raise
                except ProviderChargedFailure as error:
                    ledger = ledger.record_provider_failure(identity.ordinal, error.usage)
                    recorded_failures.append(
                        ProviderFailureRecord(
                            identity,
                            error.diagnostic,
                            1,
                            error.usage.input_tokens,
                            error.usage.output_tokens,
                            error.usage.cost,
                        )
                    )
                    self.checkpoints.write(ledger, tuple(results), tuple(recorded_failures))
                    raise
                except Exception:
                    # Failures before a provider request are neither attempts nor calls.
                    ledger = ledger.cancel_pre_provider(identity.ordinal)
                    self.checkpoints.write(ledger, tuple(results), tuple(recorded_failures))
                    raise
                ledger = ledger.reconcile_success(identity.ordinal, outcome.usage)
                assessment = self.processor.process(request, outcome.response)
                results.append(
                    ExecutionResult(
                        identity,
                        ExecutionStatus.COMPLETE,
                        1,
                        outcome.usage.input_tokens,
                        outcome.usage.output_tokens,
                        outcome.usage.cost,
                        Decimal("0"),
                        assessment.patch_extraction,
                        assessment.validation,
                        assessment.sandbox_evaluation,
                        assessment.architecture_evaluation,
                        assessment.classification,
                        assessment.diagnostic_fingerprints,
                    )
                )
                self.checkpoints.write(ledger, tuple(results), tuple(recorded_failures))
        finally:
            cleaned = self.cleanup_adapter.cleanup()
        return ledger, tuple(results), tuple(recorded_failures), cleaned
