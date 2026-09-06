# Explicit architecture constraint DSL v1

An architecture profile is a user-authored specification, never inferred from code. A component is
an explicit module family: it may represent a layer, bounded context or package group. See the
[profile schema](../schemas/architecture-profile-v1.md) and runnable
[example](../../examples/architecture/simple-layered.yaml).

## Identity and controls

The YAML requires `architecture_profile_schema_version: "1"`, `id`, `name`, `components`, and `rules`.
`description` is optional. Assignment defaults are `unassigned: warn`, `ambiguous: error`.
IDs use `[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*`, at most 128 characters. Profile/component/rule IDs
are validated; duplicate component or rule IDs fail. Component records contain `id` and `selectors`.
Names and descriptions are bounded single-line text (up to 4,096 characters); the name is nonempty.

Every rule has `id`, `type`, `severity` (default `error`), `enabled` (default `true`),
`description` (default null) and `include_type_checking` (default `true`). Severity is exactly
`info`, `warning` or `error`. Canonical JSON includes all defaults. Disabled rules remain in the
profile, fingerprint and report counts, but produce no violations.

Collections are canonicalized by component/rule ID. Selectors and component-reference collections
are sorted and deduplicated. Declaration order and YAML mapping order have no semantic significance.
Empty `rules` is valid; an empty component collection or component selector collection is invalid.

## Selectors

| Type | Exact match | Descendant boundary |
| --- | --- | --- |
| `module_exact` | Dotted Python module name | None |
| `module_prefix` | Dotted Python module name | `<value>.` |
| `path_exact` | Normalized repository-relative POSIX file path | None |
| `path_prefix` | Normalized repository-relative POSIX path | `<value>/` |

`demo.api` matches `demo.api` and `demo.api.users` under `module_prefix`, but not `demo.apiv2`.
`src/demo/api` matches itself and `src/demo/api/users.py` under `path_prefix`, but not
`src/demo/apiv2/users.py`. Paths reject absolute paths, traversal, backslashes, control characters
and glob metacharacters. No regex, glob, negation, boolean expression or source predicate exists.
Selector values are bounded to 1,024 characters. Multiple selectors in one component are an OR;
matching two selectors within one component still gives one component match.

## Assignment and completeness

Every unique internal module node is assigned the sorted set of matching component IDs. Exactly
one match is assigned; zero is unassigned; more than one is ambiguous. Declaration order never
breaks ties. External nodes are excluded. Invalid or ambiguous module identities omitted by the
graph cannot be assigned; graph partial status is propagated.

`ignore` suppresses the assignment diagnostic, `warn` emits a warning, and `error` emits an error
that fails conformance. Diagnostics contain a safe module ID, matching component IDs, category,
severity and a fixed message. They are separate from top-level rule violations and their severity
counts. Assignment counts always include ignored cases.

Incomplete assignment never grants dependency permission. A dependency rule is skipped in its
entirety when its selected edge set contains an unknown/ambiguous source, or when a uniquely
matched rule source imports an unknown/ambiguous internal target. External rules only need source
assignment. Cycle rules conservatively skip if any internal module lacks unique assignment. No
findings are emitted for a skipped rule. This avoids presenting a partially checked rule as fully
evaluated and avoids double-counting missing assignment as a dependency violation. A skipped rule
makes the report partial even when assignment policy is `ignore`. An unused unassigned module alone
does not make a dependency-only report partial; any ambiguity does.

## Four rule types

| Type | Required configuration | Violation condition |
| --- | --- | --- |
| `forbid_dependency` | `source`, `target` | Internal import crosses that exact component pair |
| `allow_only_dependencies` | `source`, `allowed` | Internal target component is absent from the permitted set |
| `forbid_external_dependency` | `source`, nonempty `external` | External target matches any explicit external selector |
| `forbid_cycles` | Nonempty `components` | Cyclic internal import SCC in the induced selected scope |

Internal dependency rules ignore external imports. Self-component dependencies are permitted by
`forbid_dependency` unless source and target explicitly name the same component. An
`allow_only_dependencies` rule is a complete internal target policy: include the source component
to permit same-component imports; `allowed: []` forbids all internal imports from that source.
Undefined references and fields belonging to a different rule type are rejected. Separate rules
remain independent even when their restrictions overlap; each rule may intentionally report its own
finding. An allow-only rule does not override another rule's explicit prohibition.

External selectors support only `external_exact` and `external_prefix`. Prefix matching includes
the exact name and descendants separated by `.`. `fastapi` matches `fastapi.routing`, not
`fastapi_utils`. Overlapping matching selectors yield one dependency violation with all matched
selector identities. Names are graph textual module names, never PyPI distribution identities.
All external rules are conservatively skipped with `external_names_collapsed` on a `top_level`
graph, including simple selectors: schema v1 requires full textual names for complete evaluation.

Cycle rules use the same iterative Kosaraju SCC implementation as graph queries. Only internal
import edges with both endpoints in selected components participate. A singleton is cyclic only
with a self-loop. One rule may span multiple components. Cycles outside scope are not violations.
With `include_type_checking: false`, evaluation uses runtime-only edges. With it enabled,
`type_checking_only` is true when removing TYPE_CHECKING edges removes every cycle in the SCC;
a mixed SCC containing any runtime cycle is false. This is a syntax classification, not a claim
about actual runtime execution.

## Granularity and conformance

Dependency findings aggregate by `(rule ID, source module ID, target module ID)`. Repeated imports
contribute ordered edge IDs, locations and `occurrence_count`, not additional top-level violations.
Exact duplicate metadata still has distinct Phase 3 occurrence-ranked edge IDs. Location order is
edge-ID order, preserving the mapping even if line numbers are not ascending. Cycle findings are
one per deterministic cyclic SCC per rule, with sorted members and participating import-edge IDs.

A report passes if it has no error-level violations and no error assignment diagnostics. Warnings
and information do not fail. `passed` and `partial` are independent facts. Graph partial input,
ambiguous assignment or any skipped rule makes a report partial. The CLI refuses successful
conformance exit for a partial report unless `--allow-partial` is explicitly supplied; it always
writes the valid report first. See [engine](constraint-engine.md) for exit-code precedence.
