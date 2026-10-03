"""Phase 12.8B immutable acquisition and source-free evidence contracts."""

from dataclasses import asdict, dataclass
from typing import Any

from archguard.domain.orchestration import fingerprint
from archguard.domain.readiness import git_sha1_commit, sha256_digest
from archguard.domain.repository import check

ACQUISITION_SCHEMA = "archguard.phase-12.8b-acquisition/v1"
LICENSE_REGISTRY_SCHEMA = "archguard.phase-12.8b-license-evidence/v1"
GRAPH_EVIDENCE_SCHEMA = "archguard.phase-12.8b-graph-evidence/v1"
DETERMINISM_SCHEMA = "archguard.phase-12.8b-graph-determinism/v1"
MANIFEST_SCHEMA = "archguard.phase-12.8b-evidence-manifest/v1"
ARCHIVE_MEMBERS = frozenset(
    {
        "manifest.json",
        "acquisition-summary.json",
        "license-evidence.json",
        "graph-evidence.json",
        "graph-determinism.json",
        "security-scan-summary.json",
        "cleanup-summary.json",
        "readiness-summary.json",
        "SHA256SUMS",
    }
)


@dataclass(frozen=True)
class ImmutableRevision:
    subject: str
    repository: str
    revision: str

    def __post_init__(self) -> None:
        check(self.subject.replace("-", "").isalnum(), "invalid acquisition subject")
        check(
            self.repository.startswith("https://github.com/") and self.repository.endswith(".git"),
            "unsupported acquisition repository",
        )
        git_sha1_commit(self.revision)


@dataclass(frozen=True)
class Phase128BManifest:
    schema: str
    task_id: str
    project: str
    buggy_revision: str
    fixed_revision: str
    framework_revision: str
    acquisition_fingerprint: str
    license_fingerprint: str
    graph_fingerprint: str
    profile_fingerprint: str
    github_run_id: str
    github_job: str
    phase_13_ready: bool
    fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == MANIFEST_SCHEMA, "unsupported Phase 12.8B manifest")
        check(self.task_id == "PySnooper-2" and self.project == "PySnooper", "wrong pilot")
        for revision in (self.buggy_revision, self.fixed_revision, self.framework_revision):
            git_sha1_commit(revision)
        for value in (
            self.acquisition_fingerprint,
            self.license_fingerprint,
            self.graph_fingerprint,
            self.profile_fingerprint,
        ):
            sha256_digest(value)
        check(not self.phase_13_ready, "Phase 13 readiness cannot be asserted by Phase 12.8B")
        identity = fingerprint({k: v for k, v in asdict(self).items() if k != "fingerprint"})
        object.__setattr__(self, "fingerprint", self.fingerprint or identity)
        check(self.fingerprint == identity, "manifest fingerprint mismatch")


def fingerprinted(schema: str, body: dict[str, Any]) -> dict[str, Any]:
    """Create a canonical domain-bound record with a deterministic fingerprint."""
    value = {"schema": schema, **body}
    value["fingerprint"] = fingerprint(value)
    return value
