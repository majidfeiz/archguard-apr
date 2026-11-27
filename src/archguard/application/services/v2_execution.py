"""Sequential, zero-retry orchestration for the frozen V2.2 call plan."""

from __future__ import annotations

from decimal import Decimal

from archguard.application.ports.v2_execution import (
    CandidateProcessor,
    CheckpointStore,
    Cleanup,
    Provider,
    ProviderChargedFailure,
    RequestPreparer,
)
from archguard.domain.v2_execution import (
    BudgetLedger,
    ExecutionResult,
    ExecutionStatus,
    StageStatus,
    TerminalClassification,
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
    ) -> tuple[BudgetLedger, tuple[ExecutionResult, ...], bool]:
        ledger = ledger or BudgetLedger()
        if tuple(item.identity.ordinal for item in carried) != ledger.completed_ordinals:
            raise ValueError("checkpoint results contradict ledger")
        results = list(carried)
        self.checkpoints.write(ledger, tuple(results))
        cleaned = False
        try:
            for identity in frozen_identities()[ledger.completed_calls :]:
                # Preparation happens before reservation, so it can never count as a provider call.
                request = self.preparer.prepare(identity)
                ledger = ledger.reserve(identity.ordinal)
                try:
                    outcome = self.provider.invoke(request)
                except ProviderChargedFailure as error:
                    ledger = ledger.reconcile(identity.ordinal, error.usage)
                    results.append(
                        ExecutionResult(
                            identity,
                            ExecutionStatus.FAILED,
                            1,
                            error.usage.input_tokens,
                            error.usage.output_tokens,
                            error.usage.cost,
                            Decimal("0"),
                            StageStatus.NOT_RUN,
                            StageStatus.NOT_RUN,
                            StageStatus.NOT_RUN,
                            StageStatus.NOT_RUN,
                            TerminalClassification.INFRASTRUCTURE_FAILURE,
                            (error.diagnostic_fingerprint,),
                        )
                    )
                    self.checkpoints.write(ledger, tuple(results))
                    raise
                except Exception:
                    # An exception without trustworthy usage is not claimed as a provider call.
                    ledger = ledger.cancel_pre_provider(identity.ordinal)
                    self.checkpoints.write(ledger, tuple(results))
                    raise
                ledger = ledger.reconcile(identity.ordinal, outcome.usage)
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
                self.checkpoints.write(ledger, tuple(results))
        finally:
            cleaned = self.cleanup_adapter.cleanup()
        return ledger, tuple(results), cleaned
