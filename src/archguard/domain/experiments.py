"""Immutable, source-free contracts for controlled pilot experiments."""

from dataclasses import asdict, dataclass
from enum import StrEnum

from archguard.domain.benchmark import DatasetSplit
from archguard.domain.orchestration import ArtifactReference, fingerprint, valid_id
from archguard.domain.repository import check, digest, safe_path

CONFIG_SCHEMA = "archguard.system-configuration/v1"
CONTRACT_SCHEMA = "archguard.comparison-contract/v1"
SCHEDULE_SCHEMA = "archguard.experiment-schedule/v1"
RUN_SCHEMA = "archguard.experiment-run/v1"
METRICS_SCHEMA = "archguard.run-metrics/v1"
LEDGER_SCHEMA = "archguard.experiment-ledger/v1"
SUMMARY_SCHEMA = "archguard.pilot-summary/v1"
FAIRNESS_SCHEMA = "archguard.fairness-report/v1"


class ExperimentMode(StrEnum):
    OFFLINE = "offline"
    EXTERNAL_PILOT = "external-pilot"
    LIVE_PILOT = "live-pilot"


class CompletionState(StrEnum):
    PLANNED = "planned"
    COMPLETED = "completed"
    UNRESOLVED = "unresolved"
    SYSTEM_FAILURE = "system_failure"
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"
    MISSING = "missing"
    CANCELLED = "cancelled"


class FailureReason(StrEnum):
    NONE = "none"
    PROVIDER_REFUSAL = "provider_refusal"
    RATE_LIMIT = "rate_limit"
    PROVIDER_OUTAGE = "provider_outage"
    AUTHENTICATION_FAILURE = "authentication_failure"
    MALFORMED_OUTPUT = "malformed_output"
    SANDBOX_TIMEOUT = "sandbox_timeout"
    BUILD_FAILURE = "build_failure"
    TEST_NONDETERMINISM = "test_nondeterminism"
    EVALUATOR_FAILURE = "evaluator_failure"
    TASK_SETUP_FAILURE = "task_setup_failure"
    BUDGET_EXHAUSTION = "budget_exhaustion"
    USER_CANCELLATION = "user_cancellation"


@dataclass(frozen=True)
class SystemConfiguration:
    schema: str
    configuration_id: str
    provider: str
    model: str
    model_revision: str
    prompt_version: str
    context_budget: int
    output_budget: int
    candidate_budget: int
    round_budget: int
    timeout_seconds: int
    sandbox_image: str
    retry_policy: str
    graph_retrieval: bool
    architecture_awareness: bool
    multi_agent: bool
    execution_feedback: bool
    iterative_refinement: bool
    evidence_ranking: bool
    configuration_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == CONFIG_SCHEMA, "unsupported system configuration schema")
        valid_id(self.configuration_id)
        check(
            all(value.strip() for value in (self.provider, self.model, self.prompt_version)),
            "empty configuration metadata",
        )
        check(
            all(
                value > 0
                for value in (
                    self.context_budget,
                    self.output_budget,
                    self.candidate_budget,
                    self.round_budget,
                    self.timeout_seconds,
                )
            ),
            "invalid configuration budget",
        )
        expected = fingerprint(
            {
                key: value
                for key, value in asdict(self).items()
                if key != "configuration_fingerprint"
            }
        )
        if self.configuration_fingerprint:
            check(self.configuration_fingerprint == expected, "configuration fingerprint mismatch")
        else:
            object.__setattr__(self, "configuration_fingerprint", expected)


@dataclass(frozen=True)
class ComparisonContract:
    schema: str
    contract_id: str
    benchmark_snapshot: ArtifactReference
    split_manifest: ArtifactReference
    task_ids: tuple[str, ...]
    configurations: tuple[SystemConfiguration, ...]
    architecture_profiles: ArtifactReference
    repetition_count: int
    seed: int
    task_order: tuple[str, ...]
    retry_policy: str
    missing_data_policy: str
    cost_policy: str
    metric_definitions: ArtifactReference
    hardware_class: str
    evaluation_tests: ArtifactReference
    contract_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == CONTRACT_SCHEMA, "unsupported comparison contract schema")
        valid_id(self.contract_id)
        check(
            self.repetition_count > 0 and self.seed >= 0, "invalid experiment repetitions or seed"
        )
        check(
            tuple(sorted(set(self.task_ids))) == self.task_ids, "task IDs must be unique and sorted"
        )
        check(
            set(self.task_order) == set(self.task_ids)
            and len(self.task_order) == len(self.task_ids),
            "invalid task order",
        )
        check(
            tuple(sorted(self.configurations, key=lambda item: item.configuration_id))
            == self.configurations,
            "configurations must be sorted",
        )
        check(
            len({item.configuration_id for item in self.configurations})
            == len(self.configurations),
            "duplicate configuration",
        )
        expected = fingerprint(
            {key: value for key, value in asdict(self).items() if key != "contract_fingerprint"}
        )
        if self.contract_fingerprint:
            check(self.contract_fingerprint == expected, "comparison contract fingerprint mismatch")
        else:
            object.__setattr__(self, "contract_fingerprint", expected)


@dataclass(frozen=True)
class FairnessDifference:
    configuration_id: str
    field: str
    expected: str
    actual: str
    permitted: bool


@dataclass(frozen=True)
class FairnessReport:
    schema: str
    comparable: bool
    differences: tuple[FairnessDifference, ...]
    report_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == FAIRNESS_SCHEMA, "unsupported fairness report schema")
        check(
            tuple(sorted(self.differences, key=lambda item: (item.configuration_id, item.field)))
            == self.differences,
            "fairness differences must be sorted",
        )
        check(
            self.comparable == all(item.permitted for item in self.differences),
            "invalid comparable status",
        )
        expected = fingerprint(
            {key: value for key, value in asdict(self).items() if key != "report_fingerprint"}
        )
        if self.report_fingerprint:
            check(self.report_fingerprint == expected, "fairness fingerprint mismatch")
        else:
            object.__setattr__(self, "report_fingerprint", expected)


@dataclass(frozen=True, order=True)
class ScheduledRun:
    block_index: int
    configuration_id: str
    task_id: str
    repetition_id: int
    run_seed: int
    run_id: str

    def __post_init__(self) -> None:
        valid_id(self.configuration_id)
        valid_id(self.task_id)
        digest(self.run_id)
        check(
            self.block_index >= 0 and self.repetition_id >= 1 and self.run_seed >= 0,
            "invalid scheduled run",
        )


@dataclass(frozen=True)
class ExperimentSchedule:
    schema: str
    experiment_plan: ArtifactReference
    comparison_contract: ArtifactReference
    runs: tuple[ScheduledRun, ...]
    schedule_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == SCHEDULE_SCHEMA, "unsupported schedule schema")
        check(
            tuple(sorted(self.runs, key=lambda item: item.block_index)) == self.runs,
            "schedule block order is not canonical",
        )
        check(len({item.run_id for item in self.runs}) == len(self.runs), "duplicate scheduled run")
        expected = fingerprint(
            {key: value for key, value in asdict(self).items() if key != "schedule_fingerprint"}
        )
        if self.schedule_fingerprint:
            check(self.schedule_fingerprint == expected, "schedule fingerprint mismatch")
        else:
            object.__setattr__(self, "schedule_fingerprint", expected)


@dataclass(frozen=True)
class RunMetrics:
    schema: str
    run_id: str
    task_resolved: bool | None
    target_failures_fixed: int | None
    regressions_introduced: int | None
    architecture_accepted: bool | None
    architecture_violation_delta: int | None
    applicable_candidate: bool | None
    valid_candidate: bool | None
    candidate_count: int | None
    repair_rounds: int | None
    malformed_outputs: int
    duplicate_candidates: int
    protected_path_rejections: int
    provider_invocations: int
    input_units: int | None
    output_units: int | None
    cached_units: int | None
    estimated_cost_microunits: int | None
    price_table_version: str | None
    duration_milliseconds: int | None
    sandbox_executions: int
    context_bytes: int
    retrieved_files: int
    retrieved_symbols: int
    retrieved_nodes: int
    retrieved_edges: int
    metrics_fingerprint: str = ""

    def __post_init__(self) -> None:
        digest(self.run_id)
        check(self.schema == METRICS_SCHEMA, "unsupported metrics schema")
        numeric = tuple(
            value
            for key, value in asdict(self).items()
            if key
            not in {
                "schema",
                "run_id",
                "task_resolved",
                "architecture_accepted",
                "applicable_candidate",
                "valid_candidate",
                "price_table_version",
                "metrics_fingerprint",
            }
            and value is not None
        )
        check(all(isinstance(value, int) for value in numeric), "metric must be an integer")
        expected = fingerprint(
            {key: value for key, value in asdict(self).items() if key != "metrics_fingerprint"}
        )
        if self.metrics_fingerprint:
            check(self.metrics_fingerprint == expected, "metrics fingerprint mismatch")
        else:
            object.__setattr__(self, "metrics_fingerprint", expected)


@dataclass(frozen=True)
class ExperimentRun:
    schema: str
    experiment_plan: ArtifactReference
    comparison_contract: ArtifactReference
    benchmark_snapshot: ArtifactReference
    configuration_id: str
    task_id: str
    repetition_id: int
    run_seed: int
    provider_model: str
    prompt_version: str
    completion_state: CompletionState
    retry_history: tuple[str, ...]
    repair_run: ArtifactReference | None
    selected_candidate: ArtifactReference | None
    evaluation_evidence: ArtifactReference | None
    metrics_record: ArtifactReference | None
    failure_reason: FailureReason
    resource_telemetry: ArtifactReference | None
    run_id: str = ""

    def __post_init__(self) -> None:
        valid_id(self.configuration_id)
        valid_id(self.task_id)
        check(self.repetition_id >= 1 and self.run_seed >= 0, "invalid run identity")
        check(
            (self.completion_state in {CompletionState.COMPLETED, CompletionState.UNRESOLVED})
            == (self.metrics_record is not None),
            "metrics/state mismatch",
        )
        check(
            (self.failure_reason == FailureReason.NONE)
            == (
                self.completion_state
                not in {
                    CompletionState.SYSTEM_FAILURE,
                    CompletionState.INFRASTRUCTURE_FAILURE,
                    CompletionState.MISSING,
                    CompletionState.CANCELLED,
                }
            ),
            "failure classification mismatch",
        )
        expected = fingerprint(
            {
                "plan": self.experiment_plan.sha256,
                "contract": self.comparison_contract.sha256,
                "configuration": self.configuration_id,
                "task": self.task_id,
                "repetition": self.repetition_id,
                "provider_model": self.provider_model,
                "prompt": self.prompt_version,
                "snapshot": self.benchmark_snapshot.sha256,
            }
        )
        if self.run_id:
            check(self.run_id == expected, "run identity mismatch")
        else:
            object.__setattr__(self, "run_id", expected)


@dataclass(frozen=True)
class LedgerEntry:
    run_id: str
    configuration_id: str
    task_id: str
    repetition_id: int
    status: CompletionState
    artifact: ArtifactReference
    failure_reason: FailureReason
    protocol_deviation: str | None = None


@dataclass(frozen=True)
class ExperimentLedger:
    schema: str
    experiment_id: str
    plan_fingerprint: str
    contract_fingerprint: str
    environment_fingerprint: str
    entries: tuple[LedgerEntry, ...]
    ledger_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == LEDGER_SCHEMA, "unsupported ledger schema")
        valid_id(self.experiment_id)
        for value in (
            self.plan_fingerprint,
            self.contract_fingerprint,
            self.environment_fingerprint,
        ):
            digest(value)
        check(
            len({item.run_id for item in self.entries}) == len(self.entries), "duplicate ledger run"
        )
        expected = fingerprint(
            {key: value for key, value in asdict(self).items() if key != "ledger_fingerprint"}
        )
        if self.ledger_fingerprint:
            check(self.ledger_fingerprint == expected, "ledger fingerprint mismatch")
        else:
            object.__setattr__(self, "ledger_fingerprint", expected)


@dataclass(frozen=True)
class PilotSummary:
    schema: str
    labels: tuple[str, ...]
    intention_to_run: tuple[tuple[str, int, int, int], ...]
    valid_run_sensitivity: tuple[tuple[str, int, int], ...]
    missing_count: int
    infrastructure_failure_count: int
    summary_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == SUMMARY_SCHEMA, "unsupported summary schema")
        check(tuple(sorted(set(self.labels))) == self.labels, "summary labels must be sorted")
        expected = fingerprint(
            {key: value for key, value in asdict(self).items() if key != "summary_fingerprint"}
        )
        if self.summary_fingerprint:
            check(self.summary_fingerprint == expected, "summary fingerprint mismatch")
        else:
            object.__setattr__(self, "summary_fingerprint", expected)


@dataclass(frozen=True)
class DescriptiveStatistics:
    count: int
    missing: int
    minimum: int | None
    first_quartile: int | None
    median: int | None
    third_quartile: int | None
    maximum: int | None

    def __post_init__(self) -> None:
        check(self.count >= 0 and self.missing >= 0, "invalid descriptive counts")
        check((self.count == 0) == (self.median is None), "invalid empty distribution")


def validate_output_directory(value: str) -> None:
    safe_path(value)


def require_pilot_split(split: DatasetSplit) -> None:
    check(
        split in {DatasetSplit.DEVELOPMENT, DatasetSplit.PILOT},
        "evaluation split is inaccessible in Phase 12",
    )
