"""Source-free evidence and self-validating canonical conformance reports."""

import hashlib
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Literal

from archguard.domain.architecture_profile import ArchitectureProfile
from archguard.domain.canonical import canonical_json
from archguard.domain.enums import Severity
from archguard.domain.graph import EdgeKind, GraphEdge, Resolution
from archguard.domain.repository import check, digest, dotted_name, safe_path

REPORT_SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class ComponentAssignment:
    module_id: str
    component_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        check(
            self.module_id.startswith("module:") and dotted_name(self.module_id[7:]),
            "invalid assigned module",
        )
        object.__setattr__(self, "component_ids", tuple(self.component_ids))
        check(self.component_ids == tuple(sorted(set(self.component_ids))), "unordered matches")


@dataclass(frozen=True)
class AssignmentEvidence:
    module_id: str
    component_ids: tuple[str, ...]
    category: Literal["unassigned", "ambiguous"]
    severity: Severity
    message: str = "Module assignment is incomplete."

    def __post_init__(self) -> None:
        ComponentAssignment(self.module_id, self.component_ids)
        object.__setattr__(self, "component_ids", tuple(self.component_ids))
        check(self.category in {"unassigned", "ambiguous"}, "invalid assignment category")
        check(self.message == "Module assignment is incomplete.", "invalid diagnostic message")


@dataclass(frozen=True, order=True)
class ImportLocation:
    edge_id: str
    path: str
    line: int
    column: int

    def __post_init__(self) -> None:
        safe_path(self.path)
        check(self.line > 0 and self.column >= 0, "invalid evidence location")
        check(self.edge_id.startswith("edge:"), "invalid edge reference")
        digest(self.edge_id[5:])


@dataclass(frozen=True)
class DependencyEvidence:
    source_module_id: str
    target_module_id: str
    source_component: str
    target_component: str | None
    external_selectors: tuple[str, ...]
    edge_ids: tuple[str, ...]
    occurrence_count: int
    locations: tuple[ImportLocation, ...]

    def __post_init__(self) -> None:
        for field in ("external_selectors", "edge_ids", "locations"):
            object.__setattr__(self, field, tuple(getattr(self, field)))
        check(
            bool(self.edge_ids) and self.edge_ids == tuple(sorted(set(self.edge_ids))),
            "invalid evidence edge order",
        )
        check(
            self.occurrence_count == len(self.edge_ids) == len(self.locations),
            "evidence occurrence mismatch",
        )
        check(
            tuple(location.edge_id for location in self.locations) == self.edge_ids,
            "location edge mismatch",
        )


@dataclass(frozen=True)
class CycleEvidence:
    module_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    type_checking_only: bool
    component_scope: tuple[str, ...]

    def __post_init__(self) -> None:
        for field in ("module_ids", "edge_ids", "component_scope"):
            values = tuple(getattr(self, field))
            check(bool(values) and values == tuple(sorted(set(values))), "invalid cycle order")
            object.__setattr__(self, field, values)


type ViolationCategory = Literal["dependency", "external_dependency", "cycle"]
VIOLATION_MESSAGES = {
    "dependency": "Internal dependency violates the explicit component policy.",
    "external_dependency": "External import matches a forbidden selector.",
    "cycle": "Internal import cycle violates the explicit component scope.",
}


@dataclass(frozen=True)
class ArchitectureViolation:
    violation_id: str
    rule_id: str
    severity: Severity
    category: ViolationCategory
    message: str
    evidence: DependencyEvidence | CycleEvidence

    def __post_init__(self) -> None:
        check(self.category in VIOLATION_MESSAGES, "invalid violation category")
        check(self.message == VIOLATION_MESSAGES[self.category], "invalid violation message")
        check(
            isinstance(self.evidence, CycleEvidence) == (self.category == "cycle"),
            "invalid evidence category",
        )


def violation_identity(
    graph_fingerprint: str,
    profile_fingerprint: str,
    rule_id: str,
    category: ViolationCategory,
    evidence: DependencyEvidence | CycleEvidence,
) -> str:
    return (
        "violation:"
        + hashlib.sha256(
            canonical_json(
                {
                    "architecture_report_schema_version": REPORT_SCHEMA_VERSION,
                    "graph_fingerprint": graph_fingerprint,
                    "profile_fingerprint": profile_fingerprint,
                    "rule_id": rule_id,
                    "category": category,
                    "evidence": asdict(evidence),
                }
            )
        ).hexdigest()
    )


@dataclass(frozen=True)
class RuleEvaluation:
    rule_id: str
    status: Literal["evaluated", "skipped", "disabled"]
    reason: Literal["complete", "incomplete_assignments", "external_names_collapsed", "disabled"]


@dataclass(frozen=True)
class ArchitectureSummary:
    internal_module_count: int
    assigned_module_count: int
    unassigned_module_count: int
    ambiguous_module_count: int
    enabled_rules: int
    disabled_rules: int
    evaluated_rules: int
    skipped_rules: int
    informational_violation_count: int
    warning_violation_count: int
    error_violation_count: int
    dependency_violation_count: int
    external_dependency_violation_count: int
    cycle_violation_count: int
    total_violation_count: int
    passed: bool
    partial: bool


def summarize_report(
    assignments: tuple[ComponentAssignment, ...],
    diagnostics: tuple[AssignmentEvidence, ...],
    results: tuple[RuleEvaluation, ...],
    violations: tuple[ArchitectureViolation, ...],
    input_partial: bool,
) -> ArchitectureSummary:
    severity = Counter(v.severity for v in violations)
    categories = Counter(v.category for v in violations)
    states = Counter(r.status for r in results)
    ambiguous = sum(len(a.component_ids) > 1 for a in assignments)
    return ArchitectureSummary(
        len(assignments),
        sum(len(a.component_ids) == 1 for a in assignments),
        sum(not a.component_ids for a in assignments),
        ambiguous,
        len(results) - states["disabled"],
        states["disabled"],
        states["evaluated"],
        states["skipped"],
        severity[Severity.INFO],
        severity[Severity.WARNING],
        severity[Severity.ERROR],
        categories["dependency"],
        categories["external_dependency"],
        categories["cycle"],
        len(violations),
        not severity[Severity.ERROR] and not any(d.severity == Severity.ERROR for d in diagnostics),
        input_partial or bool(ambiguous) or bool(states["skipped"]),
    )


@dataclass(frozen=True)
class ArchitectureReport:
    architecture_report_schema_version: str
    graph_fingerprint: str
    profile_fingerprint: str
    profile: ArchitectureProfile
    input_partial: bool
    assignments: tuple[ComponentAssignment, ...]
    assignment_diagnostics: tuple[AssignmentEvidence, ...]
    rule_results: tuple[RuleEvaluation, ...]
    evidence_edges: tuple[GraphEdge, ...]
    violations: tuple[ArchitectureViolation, ...]
    summary: ArchitectureSummary
    report_fingerprint: str

    def __post_init__(self) -> None:
        from archguard.domain.architecture_validation import validate_report

        check(
            self.architecture_report_schema_version == REPORT_SCHEMA_VERSION,
            "unsupported report schema",
        )
        digest(self.graph_fingerprint)
        check(
            self.profile_fingerprint == self.profile.profile_fingerprint,
            "report profile fingerprint mismatch",
        )
        for field in (
            "assignments",
            "assignment_diagnostics",
            "rule_results",
            "evidence_edges",
            "violations",
        ):
            object.__setattr__(self, field, tuple(getattr(self, field)))
        check(
            self.summary
            == summarize_report(
                self.assignments,
                self.assignment_diagnostics,
                self.rule_results,
                self.violations,
                self.input_partial,
            ),
            "report summary mismatch",
        )
        validate_report(self)
        check(self.report_fingerprint == report_identity(self), "report fingerprint mismatch")

    @classmethod
    def create(
        cls,
        graph_fingerprint: str,
        profile: ArchitectureProfile,
        input_partial: bool,
        assignments: tuple[ComponentAssignment, ...],
        diagnostics: tuple[AssignmentEvidence, ...],
        results: tuple[RuleEvaluation, ...],
        edges: tuple[GraphEdge, ...],
        violations: tuple[ArchitectureViolation, ...],
    ) -> "ArchitectureReport":
        summary = summarize_report(assignments, diagnostics, results, violations, input_partial)
        data = {
            "architecture_report_schema_version": REPORT_SCHEMA_VERSION,
            "graph_fingerprint": graph_fingerprint,
            "profile_fingerprint": profile.profile_fingerprint,
            "profile": asdict(profile),
            "input_partial": input_partial,
            "assignments": [asdict(a) for a in assignments],
            "assignment_diagnostics": [asdict(d) for d in diagnostics],
            "rule_results": [asdict(r) for r in results],
            "evidence_edges": [asdict(e) for e in edges],
            "violations": [asdict(v) for v in violations],
            "summary": asdict(summary),
        }
        return cls(
            REPORT_SCHEMA_VERSION,
            graph_fingerprint,
            profile.profile_fingerprint,
            profile,
            input_partial,
            assignments,
            diagnostics,
            results,
            edges,
            violations,
            summary,
            hashlib.sha256(canonical_json(data)).hexdigest(),
        )


def report_identity(report: ArchitectureReport) -> str:
    data = asdict(report)
    del data["report_fingerprint"]
    return hashlib.sha256(canonical_json(data)).hexdigest()


def assignment_diagnostics(
    assignments: tuple[ComponentAssignment, ...],
    profile: ArchitectureProfile,
) -> tuple[AssignmentEvidence, ...]:
    result = []
    for assignment in assignments:
        if len(assignment.component_ids) == 1:
            continue
        category: Literal["unassigned", "ambiguous"] = (
            "ambiguous" if assignment.component_ids else "unassigned"
        )
        action = getattr(profile.assignment, category)
        if action != "ignore":
            result.append(
                AssignmentEvidence(
                    assignment.module_id,
                    assignment.component_ids,
                    category,
                    Severity.ERROR if action == "error" else Severity.WARNING,
                )
            )
    return tuple(result)


def evidence_locations(edges: tuple[GraphEdge, ...]) -> tuple[ImportLocation, ...]:
    result = []
    for edge in edges:
        check(
            edge.kind == EdgeKind.IMPORTS
            and edge.resolution in {Resolution.INTERNAL, Resolution.EXTERNAL},
            "evidence requires import edges",
        )
        assert edge.import_record is not None
        record = edge.import_record
        result.append(ImportLocation(edge.identifier, record.path, record.line, record.column))
    return tuple(result)
