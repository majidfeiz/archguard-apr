"""Phase 12.8A source-free research preparation contracts."""

from dataclasses import asdict, dataclass
from enum import StrEnum
from math import comb
from typing import Any

from archguard.domain.orchestration import fingerprint, valid_id
from archguard.domain.readiness import git_sha1_commit, sha256_digest
from archguard.domain.repository import check

LICENSE_SCHEMA = "archguard.license-evidence/v1"
GRAPH_SCHEMA = "archguard.architecture-graph-evidence/v1"
CANDIDATE_SCHEMA = "archguard.candidate-registry/v1"
PILOT_SCHEMA = "archguard.qualification-pilot-plan/v1"
POWER_SCHEMA = "archguard.power-design-analysis/v1"


class LicenseSubject(StrEnum):
    FRAMEWORK = "framework"
    DATASET = "dataset"
    PROJECT = "project"


class LicenseStatus(StrEnum):
    VERIFIED = "VERIFIED"
    UNRESOLVED = "UNRESOLVED"
    INELIGIBLE = "INELIGIBLE"


@dataclass(frozen=True)
class LicenseEvidence:
    schema: str
    subject_id: str
    subject_kind: LicenseSubject
    canonical_url: str
    revision: str
    license_path: str | None
    license_sha256: str | None
    spdx: str | None
    evidence_method: str
    redistribution: LicenseStatus
    evaluator_use: LicenseStatus
    notes: str
    fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == LICENSE_SCHEMA, "unsupported license schema")
        valid_id(self.subject_id)
        check(self.canonical_url.startswith("https://"), "license URL must be canonical HTTPS")
        git_sha1_commit(self.revision)
        check(
            bool(self.evidence_method.strip()) and bool(self.notes.strip()), "incomplete evidence"
        )
        if self.license_sha256 is not None:
            sha256_digest(self.license_sha256)
            check(bool(self.license_path), "license hash requires a path")
        if self.redistribution == LicenseStatus.VERIFIED:
            check(
                self.license_sha256 is not None and self.spdx is not None,
                "verified license requires hashed text and unambiguous SPDX",
            )
        identity = fingerprint({k: v for k, v in asdict(self).items() if k != "fingerprint"})
        if self.fingerprint:
            check(self.fingerprint == identity, "license fingerprint mismatch")
        else:
            object.__setattr__(self, "fingerprint", identity)


@dataclass(frozen=True)
class GraphEvidence:
    schema: str
    status: str
    project_id: str
    revision: str
    profile_fingerprint: str
    snapshot_fingerprint: str | None
    graph_fingerprint: str | None
    module_count: int | None
    dependency_edges: int | None
    cycle_count: int | None
    ambiguous_modules: tuple[str, ...]
    unassigned_modules: tuple[str, ...]
    violation_count: int | None
    limitations: tuple[str, ...]
    fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == GRAPH_SCHEMA, "unsupported graph evidence schema")
        check(self.status in {"EXTERNAL_EXECUTION_REQUIRED", "VALIDATED"}, "invalid graph status")
        valid_id(self.project_id)
        git_sha1_commit(self.revision)
        sha256_digest(self.profile_fingerprint)
        for value in (self.snapshot_fingerprint, self.graph_fingerprint):
            if value is not None:
                sha256_digest(value)
        if self.status == "VALIDATED":
            check(
                None
                not in (
                    self.module_count,
                    self.dependency_edges,
                    self.cycle_count,
                    self.violation_count,
                ),
                "incomplete graph evidence",
            )
            check(
                not self.ambiguous_modules and not self.unassigned_modules,
                "graph assignment incomplete",
            )
        identity = fingerprint({k: v for k, v in asdict(self).items() if k != "fingerprint"})
        object.__setattr__(self, "fingerprint", self.fingerprint or identity)
        check(self.fingerprint == identity, "graph fingerprint mismatch")


@dataclass(frozen=True)
class Candidate:
    source: str
    project: str
    task_id: str
    buggy_revision: str
    fixed_revision: str
    license_record: str
    eligible: bool
    exclusion: str | None

    def __post_init__(self) -> None:
        valid_id(self.task_id)
        git_sha1_commit(self.buggy_revision)
        git_sha1_commit(self.fixed_revision)
        check(self.eligible == (self.exclusion is None), "candidate eligibility contradiction")


def select_pilot(candidates: tuple[Candidate, ...], maximum: int = 6) -> tuple[Candidate, ...]:
    """Outcome-blind deterministic round-robin stratification by project."""
    check(4 <= maximum <= 6, "pilot maximum must be 4-6")
    ordered = sorted(
        (item for item in candidates if item.eligible),
        key=lambda item: (item.source, item.project, item.task_id, item.buggy_revision),
    )
    projects = sorted({item.project for item in ordered})
    selected: list[Candidate] = []
    index = 0
    while len(selected) < maximum:
        added = False
        for project in projects:
            matches = [item for item in ordered if item.project == project]
            if index < len(matches):
                selected.append(matches[index])
                added = True
                if len(selected) == maximum:
                    break
        if not added:
            break
        index += 1
    return tuple(selected)


def exact_mcnemar_power(
    n: int, discordant_rate: float, favored_share: float, alpha: float = 0.05
) -> float:
    """Exact two-sided conditional McNemar power under prespecified assumptions."""
    check(n >= 1, "sample size must be positive")
    check(0 < discordant_rate <= 1 and 0.5 < favored_share < 1, "invalid power assumptions")
    power = 0.0
    for discordant in range(n + 1):
        p_d = (
            comb(n, discordant)
            * discordant_rate**discordant
            * (1 - discordant_rate) ** (n - discordant)
        )
        rejection = 0.0
        for favored in range(discordant + 1):
            tail = (
                sum(comb(discordant, k) for k in range(0, min(favored, discordant - favored) + 1))
                / 2**discordant
            )
            if min(1.0, 2 * tail) <= alpha:
                rejection += (
                    comb(discordant, favored)
                    * favored_share**favored
                    * (1 - favored_share) ** (discordant - favored)
                )
        power += p_d * rejection
    return round(power, 6)


def canonical_payload(schema: str, body: dict[str, Any]) -> dict[str, Any]:
    value = {"schema": schema, **body}
    value["fingerprint"] = fingerprint(value)
    return value
