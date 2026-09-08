from enum import StrEnum


class ExperimentStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ArtifactKind(StrEnum):
    MANIFEST = "manifest"
    ANALYSIS = "analysis"
    GRAPH = "graph"
    ARCHITECTURE_REPORT = "architecture_report"
    ARCHITECTURE_PROFILE = "architecture_profile"
    CANDIDATE_PATCH = "candidate_patch"
    ARCHITECTURE_DELTA = "architecture_delta"
    PATCH_VALIDATION = "patch_validation"
    RETRIEVAL_QUERY = "retrieval_query"
    RETRIEVAL_MANIFEST = "retrieval_manifest"
    CONTEXT_BUNDLE = "context_bundle"
    RETRIEVAL_EVALUATION = "retrieval_evaluation"
    LOG = "log"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
