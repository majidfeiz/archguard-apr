# Deterministic architecture conformance engine

Phase 4 evaluates explicit ArchitectureProfile v1 values against validated RepositoryGraph v1
values. It adds no inference, discovery heuristic, patch comparison, candidate worktree validation,
repair, call graph, data flow, model call, embedding, retrieval, agent, MCP/server integration,
HTTP evaluation, visualization or research benchmark. No repair-quality result is claimed.

## Boundaries and pipeline

YAML → bounded safe boundary validation → immutable canonical profile → explicit module assignment
→ pure rule evaluation → immutable ArchitectureReport v1 → canonical atomic JSON artifact.

Domain imports standard library only. Application imports its own services/ports, domain and
standard library. Infrastructure implements six neutral loader/reader/writer/evaluator contracts;
the evaluator implementation itself is a pure application service. CLI composes these services and
formats JSON. YAML and untrusted JSON decoding stay in infrastructure. Report/profile persistence
have separate typed adapters; shared low-level byte I/O follows the Phase 3 policy.

`DeterministicConstraintEvaluator.evaluate(graph, profile)` revalidates graph/profile invariants and
performs no filesystem reads, subprocess calls, target imports or execution. It indexes assignment
membership and internal/external import edges, filters each enabled rule, aggregates dependencies,
and uses the shared domain SCC utility extracted from Phase 3. Report construction validates its
own evidence and hashes. Neither evaluation nor graph construction rereads analyzed source.

`CompileArchitectureProfile` composes profile loading and profile writing. `EvaluateArchitecture`
composes graph reading, YAML profile loading, evaluation and report writing. Readers and writers
are independent ports. `ArchitectureAnalyzerPort` and `ArchitectureValidatorPort` are removed;
their path-based analysis and premature before/after signatures are not retained at 0.4.0.
See [ADR-0005](decisions/ADR-0005-versioned-constraint-dsl.md).

## CLI and exit codes

`architecture profile validate` validates YAML only; it never reads/evaluates a graph.
`profile compile` writes canonical JSON; `profile inspect` reads and validates that JSON.
`evaluate GRAPH --profile YAML --output REPORT` writes a report and emits concise deterministic JSON
with identities, artifact basename/hash and all summary counts. `inspect REPORT` emits summary,
rule results and assignment diagnostics. `violations REPORT [--severity info|warning|error]` lists
structured findings; `explain REPORT VIOLATION_ID` returns one finding. Unknown IDs fail with code 2.
Profile/report inspection supports `--sha256 EXPECTED`.

| Exit | Meaning |
| --- | --- |
| 0 | Valid inspection/compilation, or completed passing evaluation |
| 1 | Completed evaluation failed conformance |
| 2 | Invalid arguments, YAML, schema/configuration, unknown ID, or failed artifact I/O |
| 3 | Unsafe path or artifact-policy rejection |
| 4 | Valid report is partial and strict completeness is required |

Evaluation persists the report before applying exit policy. Code 4 takes precedence over code 1
for partial failing reports. `--allow-partial` permits code 0/1 based on conformance but never clears
`partial: true`. Warnings and information pass; errors in violations or assignment diagnostics fail.
The boolean `passed` alone does not prove complete evaluation. No HTTP conformance endpoint exists.

## Safety and limitations

Profiles reject all YAML anchors/aliases, duplicate keys, non-string keys and custom tags, then
use `yaml.safe_load`. Limits and unknown-field validation are documented in the
[profile schema](../schemas/architecture-profile-v1.md). Profile/report JSON readers validate
canonical shape, invariants and fingerprints, including evidence references and derived counts.
No source code is extracted into messages or evidence; user-authored profile text is retained.

Output parents must already exist. Symlink artifacts, traversal and nonregular files are rejected.
`compile` protects the YAML input; `evaluate` protects both graph and YAML inputs, including hardlink
aliases. `--protected-root ROOT` rejects output inside a known analyzed root. Pass this context when
known: portable graph artifacts deliberately do not retain absolute source roots. Low-level writers
require callers to invoke their destination-policy method with input/root context, as in Phase 3.
Writes use same-directory temporary files, flush/fsync and atomic replacement; failures clean up
unpublished temporary files. Stable trusted output parents are required; this is not a concurrent
adversarial filesystem sandbox. Replacing a previous output report is allowed for reproducible runs.

Only resolved syntax import edges are checked. Dynamic imports, reexports and runtime behavior are
outside the graph's guarantees. Partial graph status always propagates. Full textual external names
are required for external rules. Missing assignment can conservatively skip an entire rule. The DSL
cannot prove the absence of domain business logic in entrypoints or arbitrary vendor dependencies.
Existing AST architecture tests remain complementary; the self profile is not a complete architecture
proof. Artifact hashes are not signatures; original graph provenance must be retained.

## Self-hosting and engineering workload

`make architecture-self` analyzes this checkout with `configs/architecture-self.yaml`, which declares
both `src` and the independent example project's source root. All package modules map by explicit
prefix; package bootstrap modules map to entrypoints. Tests, scripts and the example map to `tests`
by explicit selectors. The profile enforces inner-layer internal targets and selected external
framework prohibitions, including TYPE_CHECKING imports. CI fails on errors or partial status and
writes only `/tmp` artifacts. This is engineering dogfooding, not scientific evaluation.

`make architecture-benchmark` constructs a fixed 500-module directed ring with two imports per
module, five explicit components and 100 forbid-dependency rules. There is no randomness (seed is
null); workload schema is `1`. It measures assignment separately and full evaluation including
validation, assignment and hashing, then reports violation count and canonical report bytes.
No fragile wall-clock limit is imposed. Cost is roughly O(M×S + R×E) plus canonical sorting,
serialization and SCC passes; memory includes the graph, profile and retained violation evidence.
See [verification](../phase-4-verification.md) for actual local measurements and environment.
