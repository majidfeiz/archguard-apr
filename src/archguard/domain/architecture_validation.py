"""Report evidence invariants, independent of persistence and repository access."""

from archguard.domain.architecture_profile import (
    AllowOnlyDependencies,
    ForbidCycles,
    ForbidDependency,
    ForbidExternalDependency,
)
from archguard.domain.architecture_report import (
    ArchitectureReport,
    CycleEvidence,
    DependencyEvidence,
    assignment_diagnostics,
    evidence_locations,
    violation_identity,
)
from archguard.domain.graph import GraphEdge, Resolution
from archguard.domain.graph_algorithms import components
from archguard.domain.repository import check, dotted_name


def cyclic_groups(
    modules: tuple[str, ...],
    edges: tuple[GraphEdge, ...],
    runtime_only: bool = False,
) -> tuple[tuple[str, ...], ...]:
    adjacency = {m: set[str]() for m in modules}
    for edge in edges:
        assert edge.import_record is not None
        if not runtime_only or not edge.import_record.type_checking:
            adjacency[edge.source].add(edge.target)
    return tuple(g for g in components(adjacency) if len(g) > 1 or g[0] in adjacency[g[0]])


def validate_report(report: ArchitectureReport) -> None:
    assignments = {a.module_id: a.component_ids for a in report.assignments}
    check(
        tuple(assignments) == tuple(sorted(assignments))
        and len(assignments) == len(report.assignments),
        "invalid assignment order",
    )
    component_ids = {c.id for c in report.profile.components}
    check(all(set(ids) <= component_ids for ids in assignments.values()), "undefined assignment")
    check(
        report.assignment_diagnostics == assignment_diagnostics(report.assignments, report.profile),
        "assignment diagnostics mismatch",
    )
    rules = {r.id: r for r in report.profile.rules}
    check(tuple(r.rule_id for r in report.rule_results) == tuple(rules), "rule result mismatch")
    results = {r.rule_id: r for r in report.rule_results}
    for result in report.rule_results:
        rule = rules[result.rule_id]
        check(result.status in {"disabled", "skipped", "evaluated"}, "invalid rule status")
        check((result.status == "disabled") == (not rule.enabled), "disabled rule mismatch")
        check(
            (result.status == "disabled" and result.reason == "disabled")
            or (result.status == "evaluated" and result.reason == "complete")
            or (
                result.status == "skipped"
                and result.reason in {"incomplete_assignments", "external_names_collapsed"}
            ),
            "invalid skip reason",
        )
        if result.reason == "external_names_collapsed":
            check(isinstance(rule, ForbidExternalDependency), "invalid external skip")
    edges = {e.identifier: e for e in report.evidence_edges}
    check(
        tuple(edges) == tuple(sorted(edges)) and len(edges) == len(report.evidence_edges),
        "invalid evidence registry",
    )
    for edge in report.evidence_edges:
        evidence_locations((edge,))
        check(edge.source in assignments, "dangling evidence source")
        if edge.resolution == Resolution.INTERNAL:
            check(edge.target in assignments, "dangling evidence target")
        else:
            check(
                edge.target.startswith("external-module:") and dotted_name(edge.target[16:]),
                "invalid external evidence target",
            )
    check(
        tuple(v.violation_id for v in report.violations)
        == tuple(sorted({v.violation_id for v in report.violations})),
        "invalid violation order",
    )
    used: set[str] = set()
    identities: set[tuple[str, ...]] = set()
    for violation in report.violations:
        check(violation.rule_id in rules, "dangling rule")
        rule = rules[violation.rule_id]
        check(results[rule.id].status == "evaluated", "unevaluated rule produced violation")
        check(violation.severity == rule.severity, "violation severity mismatch")
        evidence = violation.evidence
        check(set(evidence.edge_ids) <= edges.keys(), "dangling evidence edge")
        selected = tuple(edges[e] for e in evidence.edge_ids)
        check(
            all(
                rule.include_type_checking
                or (e.import_record is not None and not e.import_record.type_checking)
                for e in selected
            ),
            "filtered evidence",
        )
        used.update(evidence.edge_ids)
        if isinstance(evidence, DependencyEvidence):
            check(not isinstance(rule, ForbidCycles), "invalid dependency rule")
            assert not isinstance(rule, ForbidCycles)
            check(
                all(
                    (e.source, e.target) == (evidence.source_module_id, evidence.target_module_id)
                    for e in selected
                ),
                "dependency endpoints mismatch",
            )
            check(evidence.locations == evidence_locations(selected), "locations mismatch")
            check(
                assignments[evidence.source_module_id] == (evidence.source_component,)
                and evidence.source_component == rule.source,
                "source component mismatch",
            )
            identity: tuple[str, ...] = (
                rule.id,
                evidence.source_module_id,
                evidence.target_module_id,
            )
            if isinstance(rule, ForbidExternalDependency):
                check(
                    violation.category == "external_dependency"
                    and all(e.resolution == Resolution.EXTERNAL for e in selected)
                    and evidence.target_component is None,
                    "invalid external evidence",
                )
                selectors = tuple(
                    s.type + ":" + s.value
                    for s in rule.external
                    if s.matches(evidence.target_module_id[16:])
                )
                check(
                    bool(selectors) and evidence.external_selectors == selectors,
                    "external selector mismatch",
                )
            else:
                check(
                    violation.category == "dependency"
                    and not evidence.external_selectors
                    and all(e.resolution == Resolution.INTERNAL for e in selected),
                    "invalid internal evidence",
                )
                check(
                    assignments[evidence.target_module_id] == (evidence.target_component,),
                    "target component mismatch",
                )
                check(
                    (
                        isinstance(rule, ForbidDependency)
                        and rule.target == evidence.target_component
                    )
                    or (
                        isinstance(rule, AllowOnlyDependencies)
                        and evidence.target_component not in rule.allowed
                    ),
                    "allowed evidence",
                )
        else:
            check(isinstance(rule, ForbidCycles), "invalid cycle rule")
            assert isinstance(rule, ForbidCycles) and isinstance(evidence, CycleEvidence)
            check(evidence.component_scope == rule.components, "cycle scope mismatch")
            check(
                all(
                    m in assignments
                    and len(assignments[m]) == 1
                    and assignments[m][0] in rule.components
                    for m in evidence.module_ids
                ),
                "cycle membership mismatch",
            )
            check(
                all(
                    e.resolution == Resolution.INTERNAL
                    and e.source in evidence.module_ids
                    and e.target in evidence.module_ids
                    for e in selected
                ),
                "cycle endpoint mismatch",
            )
            check(
                cyclic_groups(evidence.module_ids, selected) == (evidence.module_ids,),
                "evidence is not one cyclic SCC",
            )
            check(
                evidence.type_checking_only
                == (not bool(cyclic_groups(evidence.module_ids, selected, True))),
                "cycle runtime classification mismatch",
            )
            identity = (rule.id, *evidence.module_ids)
        check(identity not in identities, "duplicate violation group")
        identities.add(identity)
        check(
            violation.violation_id
            == violation_identity(
                report.graph_fingerprint,
                report.profile_fingerprint,
                rule.id,
                violation.category,
                evidence,
            ),
            "violation ID mismatch",
        )
    check(used == edges.keys(), "unused evidence registry entries")
