"""Immutable benchmark registry, provenance, eligibility, and leakage contracts."""

import re
from dataclasses import asdict, dataclass
from enum import StrEnum

from archguard.domain.orchestration import ArtifactReference, fingerprint, valid_id
from archguard.domain.repository import check, digest, safe_path

REGISTRY_SCHEMA = "archguard.benchmark-registry/v1"
TASK_SCHEMA = "archguard.benchmark-task/v1"
SNAPSHOT_SCHEMA = "archguard.benchmark-snapshot/v1"
SPLIT_SCHEMA = "archguard.benchmark-splits/v1"
LEAKAGE_SCHEMA = "archguard.contamination-assessment/v1"
EXPERIMENT_PLAN_SCHEMA = "archguard.experiment-plan/v1"


class BenchmarkKind(StrEnum):
    BUGSINPY = "bugsinpy"
    SWEBENCH_VERIFIED = "swe-bench-verified"
    SYNTHETIC = "synthetic"


class AcquisitionPolicy(StrEnum):
    EXPLICIT_NETWORK = "explicit_network"
    OFFLINE_CACHE_ONLY = "offline_cache_only"


@dataclass(frozen=True)
class BenchmarkRegistryEntry:
    benchmark_id: str
    kind: BenchmarkKind
    benchmark_version: str
    upstream_source: str
    upstream_revision: str
    citation: str
    license_identifier: str
    license_source: str
    redistribution_status: str
    adapter_version: str
    declared_task_count: int | None
    supported_languages: tuple[str, ...]
    supported_platforms: tuple[str, ...]
    acquisition_policy: AcquisitionPolicy
    integrity_policy: str
    gold_artifact_policy: str
    cache_policy: str
    evaluator_policy: str
    known_limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        valid_id(self.benchmark_id)
        check(bool(self.benchmark_version.strip()), "empty benchmark version")
        check(self.upstream_source.startswith("https://"), "invalid upstream source")
        check(
            re.fullmatch(r"[0-9a-f]{40}", self.upstream_revision) is not None,
            "invalid upstream revision",
        )
        check(bool(self.citation.strip()), "missing benchmark citation")
        check(
            bool(self.license_identifier.strip()) and bool(self.license_source.strip()),
            "invalid license record",
        )
        check(
            self.redistribution_status in {"allowed", "restricted", "unresolved"},
            "invalid redistribution status",
        )
        check(
            self.declared_task_count is None or self.declared_task_count >= 0, "invalid task count"
        )
        check(
            all(
                value.strip()
                for value in (
                    self.integrity_policy,
                    self.gold_artifact_policy,
                    self.cache_policy,
                    self.evaluator_policy,
                )
            ),
            "incomplete benchmark policy",
        )
        check(
            tuple(sorted(set(self.supported_languages))) == self.supported_languages,
            "unordered languages",
        )
        check(
            tuple(sorted(set(self.supported_platforms))) == self.supported_platforms,
            "unordered platforms",
        )


@dataclass(frozen=True)
class BenchmarkRegistry:
    schema: str
    entries: tuple[BenchmarkRegistryEntry, ...]
    registry_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == REGISTRY_SCHEMA, "unsupported benchmark registry schema")
        check(
            tuple(sorted(self.entries, key=lambda item: item.benchmark_id)) == self.entries,
            "noncanonical registry ordering",
        )
        check(
            len({item.benchmark_id for item in self.entries}) == len(self.entries),
            "duplicate benchmark ID",
        )
        self._identity()

    def _identity(self) -> None:
        expected = fingerprint(
            {key: value for key, value in asdict(self).items() if key != "registry_fingerprint"}
        )
        if self.registry_fingerprint:
            check(self.registry_fingerprint == expected, "registry fingerprint mismatch")
        else:
            object.__setattr__(self, "registry_fingerprint", expected)


class TaskState(StrEnum):
    DISCOVERED = "discovered"
    METADATA_VALIDATED = "metadata_validated"
    ACQUIRED = "acquired"
    INTEGRITY_VERIFIED = "integrity_verified"
    ENVIRONMENT_READY = "environment_ready"
    BUG_REPRODUCED = "bug_reproduced"
    ARCHITECTURE_ANALYZED = "architecture_analyzed"
    ELIGIBLE = "eligible"
    EXCLUDED = "excluded"
    QUARANTINED = "quarantined"
    DRY_RUN_VERIFIED = "dry_run_verified"


class ExclusionReason(StrEnum):
    UNSUPPORTED_LANGUAGE = "unsupported_language"
    MISSING_LICENSE = "missing_license"
    SOURCE_UNAVAILABLE = "source_unavailable"
    REVISION_UNAVAILABLE = "revision_unavailable"
    BUILD_FAILURE = "build_failure"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    NONDETERMINISTIC_BASELINE = "nondeterministic_baseline"
    TARGET_FAILURE_NOT_REPRODUCED = "target_failure_not_reproduced"
    UNSUPPORTED_PLATFORM = "unsupported_platform"
    EXTERNAL_SERVICE_REQUIRED = "external_service_required"
    RESOURCE_LIMIT_EXCEEDED = "resource_limit_exceeded"
    ANALYSIS_FAILURE = "analysis_failure"
    GRAPH_FAILURE = "graph_failure"
    EVALUATOR_FAILURE = "evaluator_failure"
    GOLD_ISOLATION_FAILURE = "gold_isolation_failure"
    POLICY_EXCLUSION = "policy_exclusion"


class DatasetSplit(StrEnum):
    DEVELOPMENT = "development"
    PILOT = "pilot"
    EVALUATION = "evaluation"
    EXCLUDED = "excluded"


@dataclass(frozen=True)
class BenchmarkTask:
    schema: str
    task_id: str
    benchmark_id: str
    project_id: str
    instance_id: str
    language: str
    repository_url: str
    baseline_revision: str
    problem_statement: ArtifactReference
    public_tests: tuple[str, ...]
    evaluator_only_tests: tuple[ArtifactReference, ...]
    execution_environment: ArtifactReference
    architecture_profile: ArtifactReference
    state: TaskState
    exclusion_reasons: tuple[ExclusionReason, ...]
    license_identifier: str
    provenance: tuple[tuple[str, str], ...]
    integrity_hashes: tuple[str, ...]
    split: DatasetSplit
    sensitivity: str
    fixed_revision_hash: str | None = None
    gold_patch_hash: str | None = None
    task_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == TASK_SCHEMA, "unsupported benchmark task schema")
        valid_id(self.task_id)
        valid_id(self.benchmark_id)
        valid_id(self.project_id)
        valid_id(self.instance_id)
        check(self.language == "python", "unsupported benchmark language")
        check(self.repository_url.startswith("https://"), "invalid repository URL")
        check(
            re.fullmatch(r"[0-9a-f]{40}", self.baseline_revision) is not None,
            "invalid baseline revision",
        )
        check(bool(self.license_identifier.strip()), "missing task license")
        check(
            self.sensitivity in {"agent_visible", "evaluator_only", "quarantined"},
            "invalid sensitivity",
        )
        object.__setattr__(self, "public_tests", tuple(sorted(set(self.public_tests))))
        object.__setattr__(
            self, "evaluator_only_tests", tuple(sorted(set(self.evaluator_only_tests)))
        )
        object.__setattr__(self, "exclusion_reasons", tuple(sorted(set(self.exclusion_reasons))))
        object.__setattr__(self, "provenance", tuple(sorted(set(self.provenance))))
        object.__setattr__(self, "integrity_hashes", tuple(sorted(set(self.integrity_hashes))))
        check(
            (self.state == TaskState.EXCLUDED) == bool(self.exclusion_reasons),
            "invalid exclusion record",
        )
        if self.fixed_revision_hash:
            digest(self.fixed_revision_hash)
        if self.gold_patch_hash:
            digest(self.gold_patch_hash)
        expected = fingerprint(
            {key: value for key, value in asdict(self).items() if key != "task_fingerprint"}
        )
        if self.task_fingerprint:
            check(self.task_fingerprint == expected, "task fingerprint mismatch")
        else:
            object.__setattr__(self, "task_fingerprint", expected)


class ProfileState(StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    FROZEN = "frozen"
    EXCLUDED = "excluded"


@dataclass(frozen=True)
class ProfileRecord:
    task_id: str
    profile: ArtifactReference
    state: ProfileState
    author: str
    reviewer: str | None
    rationale: str
    covered_modules: int
    unassigned_modules: int

    def __post_init__(self) -> None:
        valid_id(self.task_id)
        check(
            bool(self.author.strip()) and bool(self.rationale.strip()), "incomplete profile record"
        )
        check(
            self.state != ProfileState.FROZEN or bool(self.reviewer), "frozen profile lacks review"
        )
        check(
            self.covered_modules >= 0 and self.unassigned_modules >= 0, "invalid profile coverage"
        )


@dataclass(frozen=True)
class BenchmarkSnapshot:
    schema: str
    adapter_version: str
    upstream_revision: str
    dataset_revision: str
    tasks: tuple[BenchmarkTask, ...]
    profiles: tuple[ProfileRecord, ...]
    split_manifest: ArtifactReference
    exclusion_manifest: ArtifactReference
    license_manifest: ArtifactReference
    snapshot_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == SNAPSHOT_SCHEMA, "unsupported benchmark snapshot schema")
        check(
            tuple(sorted(self.tasks, key=lambda item: item.task_id)) == self.tasks,
            "unordered benchmark tasks",
        )
        check(len({item.task_id for item in self.tasks}) == len(self.tasks), "duplicate task ID")
        check(
            tuple(sorted(self.profiles, key=lambda item: item.task_id)) == self.profiles,
            "unordered profile records",
        )
        check(bool(self.dataset_revision.strip()), "missing dataset revision")
        expected = fingerprint(
            {key: value for key, value in asdict(self).items() if key != "snapshot_fingerprint"}
        )
        if self.snapshot_fingerprint:
            check(self.snapshot_fingerprint == expected, "snapshot fingerprint mismatch")
        else:
            object.__setattr__(self, "snapshot_fingerprint", expected)


@dataclass(frozen=True)
class EligibilityEvidence:
    task_id: str
    source_available: bool
    revision_available: bool
    licensed: bool
    environment_ready: bool
    target_failure_reproduced: bool
    deterministic_baseline: bool
    architecture_analyzed: bool
    graph_constructed: bool
    evaluator_ready: bool
    gold_isolated: bool
    supported_platform: bool
    no_external_service: bool
    within_resources: bool


@dataclass(frozen=True)
class EligibilityResult:
    task_id: str
    eligible: bool
    reasons: tuple[ExclusionReason, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(sorted(set(self.reasons))))
        check(self.eligible == (not self.reasons), "invalid eligibility result")


@dataclass(frozen=True)
class SplitManifest:
    schema: str
    version: int
    seed: int
    assignments: tuple[tuple[str, DatasetSplit], ...]
    grouping: str
    frozen: bool
    split_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == SPLIT_SCHEMA, "unsupported split schema")
        check(self.version >= 1 and 0 <= self.seed <= 2**63 - 1, "invalid split version or seed")
        check(tuple(sorted(self.assignments)) == self.assignments, "unordered split assignments")
        check(
            len({task for task, _ in self.assignments}) == len(self.assignments),
            "duplicate split assignment",
        )
        check(self.grouping in {"project", "time", "project_and_duplicate"}, "unsupported grouping")
        expected = fingerprint(
            {key: value for key, value in asdict(self).items() if key != "split_fingerprint"}
        )
        if self.split_fingerprint:
            check(self.split_fingerprint == expected, "split fingerprint mismatch")
        else:
            object.__setattr__(self, "split_fingerprint", expected)


class ContaminationRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class LeakageAssessment:
    task_id: str
    signals: tuple[str, ...]
    risk: ContaminationRisk
    excluded: bool


@dataclass(frozen=True)
class LeakageAudit:
    schema: str
    assessments: tuple[LeakageAssessment, ...]
    audit_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == LEAKAGE_SCHEMA, "unsupported leakage schema")
        check(
            tuple(sorted(self.assessments, key=lambda item: item.task_id)) == self.assessments,
            "unordered leakage audit",
        )
        expected = fingerprint(
            {key: value for key, value in asdict(self).items() if key != "audit_fingerprint"}
        )
        if self.audit_fingerprint:
            check(self.audit_fingerprint == expected, "audit fingerprint mismatch")
        else:
            object.__setattr__(self, "audit_fingerprint", expected)


@dataclass(frozen=True)
class ExperimentPlan:
    schema: str
    benchmark_snapshot: ArtifactReference
    frozen_split: ArtifactReference
    system_configuration: ArtifactReference
    profile_set: ArtifactReference
    provider_configuration: ArtifactReference
    prompt_template_version: str
    execution_plan_version: str
    random_seed: int
    candidate_budget: int
    round_budget: int
    timeout_seconds: int
    repetitions: int
    baseline_configurations: tuple[str, ...]
    ablation_configurations: tuple[str, ...]
    metrics_specification: ArtifactReference
    output_directory: str
    resume_policy: str
    evaluation_tasks_frozen: bool
    profiles_frozen: bool
    plan_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == EXPERIMENT_PLAN_SCHEMA, "unsupported experiment plan schema")
        check(
            self.evaluation_tasks_frozen and self.profiles_frozen,
            "final plan requires frozen tasks and profiles",
        )
        safe_path(self.output_directory)
        check(
            all(
                1 <= value <= 1_000_000
                for value in (
                    self.candidate_budget,
                    self.round_budget,
                    self.timeout_seconds,
                    self.repetitions,
                )
            ),
            "invalid experiment budget",
        )
        check(
            "key" not in canonical_lower(asdict(self)), "credentials prohibited in experiment plan"
        )
        expected = fingerprint(
            {key: value for key, value in asdict(self).items() if key != "plan_fingerprint"}
        )
        if self.plan_fingerprint:
            check(self.plan_fingerprint == expected, "plan fingerprint mismatch")
        else:
            object.__setattr__(self, "plan_fingerprint", expected)


def canonical_lower(value: object) -> str:
    return str(value).lower()
