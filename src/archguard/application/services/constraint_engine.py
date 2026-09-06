"""Pure deterministic evaluation of validated graph and profile values."""

from collections import defaultdict

from archguard.domain.architecture_profile import (
    AllowOnlyDependencies,
    ArchitectureProfile,
    ArchitectureRule,
    ForbidCycles,
    ForbidDependency,
    ForbidExternalDependency,
)
from archguard.domain.architecture_report import (
    VIOLATION_MESSAGES,
    ArchitectureReport,
    ArchitectureViolation,
    ComponentAssignment,
    CycleEvidence,
    DependencyEvidence,
    RuleEvaluation,
    ViolationCategory,
    assignment_diagnostics,
    evidence_locations,
    violation_identity,
)
from archguard.domain.architecture_validation import cyclic_groups
from archguard.domain.graph import GraphEdge, NodeKind, RepositoryGraph, Resolution


def assign_components(
    graph: RepositoryGraph,
    profile: ArchitectureProfile,
) -> tuple[ComponentAssignment, ...]:
    return tuple(
        ComponentAssignment(
            node.identifier,
            tuple(
                c.id
                for c in profile.components
                if any(
                    s.matches(node.module_name or "", node.owner_path or "") for s in c.selectors
                )
            ),
        )
        for node in graph.nodes
        if node.kind == NodeKind.MODULE
    )


def incomplete_rule(
    rule: ArchitectureRule,
    assignments: dict[str, tuple[str, ...]],
    edges: tuple[GraphEdge, ...],
) -> bool:
    # Unknown source membership can hide relevant dependencies. Unknown targets only
    # affect internal rules. Ignore suppresses diagnostics, never invents membership.
    if isinstance(rule, ForbidCycles):
        return any(len(ids) != 1 for ids in assignments.values())
    for edge in edges:
        source = assignments[edge.source]
        if len(source) != 1:
            return True
        if (
            source == (rule.source,)
            and not isinstance(rule, ForbidExternalDependency)
            and len(assignments[edge.target]) != 1
        ):
            return True
    return False


class DeterministicConstraintEvaluator:
    def evaluate(self, graph: RepositoryGraph, profile: ArchitectureProfile) -> ArchitectureReport:
        # Revalidate value invariants even for callers bypassing frozen dataclass construction.
        graph.__post_init__()
        profile.__post_init__()
        assignments = assign_components(graph, profile)
        membership = {a.module_id: a.component_ids for a in assignments}
        results: list[RuleEvaluation] = []
        violations: list[ArchitectureViolation] = []
        used_edges: dict[str, GraphEdge] = {}
        internal = tuple(e for e in graph.edges if e.resolution == Resolution.INTERNAL)
        external = tuple(e for e in graph.edges if e.resolution == Resolution.EXTERNAL)
        for rule in profile.rules:
            if not rule.enabled:
                results.append(RuleEvaluation(rule.id, "disabled", "disabled"))
                continue
            is_external = isinstance(rule, ForbidExternalDependency)
            edges = tuple(
                e
                for e in (external if is_external else internal)
                if rule.include_type_checking
                or (e.import_record is not None and not e.import_record.type_checking)
            )
            if is_external and graph.build_options.external_names == "top_level":
                # Collapsed names cannot prove exact/prefix matching of full textual imports.
                results.append(RuleEvaluation(rule.id, "skipped", "external_names_collapsed"))
                continue
            if incomplete_rule(rule, membership, edges):
                results.append(RuleEvaluation(rule.id, "skipped", "incomplete_assignments"))
                continue
            results.append(RuleEvaluation(rule.id, "evaluated", "complete"))
            if isinstance(rule, ForbidCycles):
                modules = tuple(m for m, ids in membership.items() if ids[0] in rule.components)
                scope = set(modules)
                selected = tuple(e for e in edges if e.source in scope and e.target in scope)
                for group in cyclic_groups(modules, selected):
                    group_edges = tuple(
                        e for e in selected if e.source in group and e.target in group
                    )
                    evidence = CycleEvidence(
                        group,
                        tuple(e.identifier for e in group_edges),
                        not bool(cyclic_groups(group, group_edges, True)),
                        rule.components,
                    )
                    violations.append(make_violation(graph, profile, rule, "cycle", evidence))
                    used_edges.update((e.identifier, e) for e in group_edges)
                continue
            grouped: dict[tuple[str, str], list[GraphEdge]] = defaultdict(list)
            for edge in edges:
                if membership[edge.source] != (rule.source,):
                    continue
                if isinstance(rule, ForbidExternalDependency):
                    forbidden = any(s.matches(edge.target[16:]) for s in rule.external)
                elif isinstance(rule, ForbidDependency):
                    forbidden = membership[edge.target] == (rule.target,)
                else:
                    assert isinstance(rule, AllowOnlyDependencies)
                    forbidden = membership[edge.target][0] not in rule.allowed
                if forbidden:
                    grouped[(edge.source, edge.target)].append(edge)
            for (source, target), occurrences in sorted(grouped.items()):
                matching = tuple(occurrences)
                selectors = (
                    tuple(s.type + ":" + s.value for s in rule.external if s.matches(target[16:]))
                    if isinstance(rule, ForbidExternalDependency)
                    else ()
                )
                dependency = DependencyEvidence(
                    source,
                    target,
                    rule.source,
                    None if is_external else membership[target][0],
                    selectors,
                    tuple(e.identifier for e in matching),
                    len(matching),
                    evidence_locations(matching),
                )
                category: ViolationCategory = "external_dependency" if is_external else "dependency"
                violations.append(make_violation(graph, profile, rule, category, dependency))
                used_edges.update((e.identifier, e) for e in matching)
        return ArchitectureReport.create(
            graph.graph_fingerprint,
            profile,
            graph.summary.partial,
            assignments,
            assignment_diagnostics(assignments, profile),
            tuple(results),
            tuple(used_edges[k] for k in sorted(used_edges)),
            tuple(sorted(violations, key=lambda v: v.violation_id)),
        )


def make_violation(
    graph: RepositoryGraph,
    profile: ArchitectureProfile,
    rule: ArchitectureRule,
    category: ViolationCategory,
    evidence: DependencyEvidence | CycleEvidence,
) -> ArchitectureViolation:
    return ArchitectureViolation(
        violation_identity(
            graph.graph_fingerprint, profile.profile_fingerprint, rule.id, category, evidence
        ),
        rule.id,
        rule.severity,
        category,
        VIOLATION_MESSAGES[category],
        evidence,
    )
