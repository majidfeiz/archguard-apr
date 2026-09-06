# Architecture report schema v1

Normative values are in `domain/architecture_report.py`; cross-record checks are in
`domain/architecture_validation.py`. Schema version is independent of graph and profile versions.

| Canonical field | Value |
| --- | --- |
| architecture_report_schema_version | `"1"` |
| graph_fingerprint | Validated input graph identity |
| profile_fingerprint | Embedded profile identity |
| profile | Complete canonical ArchitectureProfile v1 for rule validation |
| input_partial | Input graph summary partial flag |
| assignments | All internal modules sorted by module ID, with sorted component IDs |
| assignment_diagnostics | Policy-derived records in module-ID order |
| rule_results | One result per profile rule, ordered by rule ID |
| evidence_edges | Unique Phase 3 import edges used by violations, sorted by ID |
| violations | Unique structured violations sorted by violation ID |
| summary | Derived counts and pass/partial status |
| report_fingerprint | SHA-256 of all preceding canonical fields |

Rule result fields: `rule_id`, `status`, `reason`. Status is `evaluated`, `skipped`, or `disabled`.
Reasons are `complete`, `incomplete_assignments`, `external_names_collapsed`, or `disabled` with
matching status. Disabled/evaluated/skipped counts must agree with these records and profile controls.
Assignment records contain `module_id` and `component_ids`. Assignment diagnostic fields are
`module_id`, `component_ids`, `category` (`unassigned`/`ambiguous`), `severity`, `message`.

Violation fields: `violation_id`, `rule_id`, `severity`, `category`, `message`, `evidence`.
Category is `dependency`, `external_dependency`, or `cycle`. Messages are fixed by category.
Dependency evidence has `source_module_id`, `target_module_id`, `source_component`,
`target_component` (null for external), `external_selectors` (matched `type:value` strings),
`edge_ids`, `occurrence_count`, `locations`. Each location contains `edge_id`, safe relative `path`,
positive `line` and nonnegative `column`. Locations are in edge-ID order and retain every occurrence.
Cycle evidence has sorted `module_ids`, `edge_ids`, `type_checking_only`, `component_scope`.
The evidence registry contains unchanged validated Phase 3 GraphEdge records, including normalized
import metadata and locations, never source lines or file contents.

Summary fields: `internal_module_count`, `assigned_module_count`, `unassigned_module_count`,
`ambiguous_module_count`, `enabled_rules`, `disabled_rules`, `evaluated_rules`, `skipped_rules`,
`informational_violation_count`, `warning_violation_count`, `error_violation_count`,
`dependency_violation_count`, `external_dependency_violation_count`, `cycle_violation_count`,
`total_violation_count`, `passed`, `partial`. Assignment diagnostic severities do not inflate
violation counts, but error diagnostics fail `passed`. The [DSL](../architecture/constraint-dsl.md)
defines granularity, skipped-rule behavior and completeness.

## Identity and validation

Canonical bytes use the same sorted-key UTF-8 JSON framing and trailing LF as profile artifacts.
Report fingerprint is SHA-256 over the complete report object excluding only `report_fingerprint`.
It includes graph/profile identities, embedded profile, assignments, diagnostics, rule statuses,
evidence registry, violations and derived summary. Artifact SHA-256 includes the report fingerprint.

Violation ID is `violation:` followed by SHA-256 of a canonical object with exactly
`architecture_report_schema_version`, `graph_fingerprint`, `profile_fingerprint`, `rule_id`,
`category`, `evidence`. Full structured evidence participates, so occurrence/location changes alter
identity, while artifact destination never does. Both hashes include the canonical trailing LF.
No timestamp, absolute checkout root, destination, insertion order or Python object hash participates.

Readers use bounded regular-file reads (64 MiB), optional expected artifact SHA-256, duplicate-key
rejection and strict typed decoding followed by exact shape comparison. Unknown fields, coercions,
nonfinite numbers and unsupported schemas fail. Validation recomputes summary, report/profile and
violation fingerprints; checks unique ordering, rule controls, assignment diagnostics, evidence
references, internal/external endpoints, locations, occurrence counts, selector matches, component
policy and cyclic SCC/runtime classification. Unused registry edges and duplicate violation groups
are rejected. Only evaluated enabled rules can have violations.

A report reader has no original graph or source. These checks establish internal consistency, not
authenticity or completeness against a malicious party recomputing every hash and removing evidence.
Retain the graph artifact and its hash for provenance and reproduce evaluation when verifying the
full result. Fingerprints are content identities, not signatures.
