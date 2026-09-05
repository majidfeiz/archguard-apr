# Deterministic repository graph

Phase 3 consumes a validated RepositorySnapshot v1; construction never opens a source file,
imports a target module, inspects installed packages or invokes a subprocess. Domain values are
frozen standard-library dataclasses. The builder and query service are pure application components;
reader/writer ports isolate infrastructure persistence. No NetworkX or runtime dependency was added.

## Structure and ownership

Exactly one `repository:root` contains every `file:<relative-path>`, including skipped and failed
files. A unique valid module identity creates `module:<dotted-name>` defined by its file. Module
nodes define top-level symbols; enclosing symbols contain their directly nested symbols. Symbols
retain Phase 2 identifiers, locations, decorators and method classification. Duplicate declarations
remain distinct by location. Invalid or ambiguous module ownership falls back to file-to-top-level-
symbol `defines` edges. Ambiguous module nodes are omitted, never merged. `declares` would duplicate
`defines` and is intentionally omitted. There is no call graph or architectural-layer classification.

## Import resolution

Plain imports require an exact unique internal module match. For `from base import item`, try
`base.item`, then `base`; never infer attributes, exports or runtime values. Encountering an
ambiguous candidate stops resolution without falling back. Wildcards target the base without
expansion. Absolute unmatched imports target `external-module:<base>`; the default `full_module`
option preserves the complete textual module prefix. The explicit `top_level` option groups by
its first component. Neither identifies an installed package or a PyPI distribution.

Relative imports derive the current package from the module: an initializer retains all components,
other files remove the final component. Level 1 stays in that package; each additional level removes
one component. A level greater than the number of package components is beyond-root. Append the
raw module and apply the same submodule/base policy. Unmatched relative imports never create
external nodes. Namespace-like directories need no initializer for exact snapshot module matching.

Every import occurrence retains the complete Phase 2 ImportSnapshot, resolution and occurrence rank.
Repeated source/target pairs remain separate edges. Exact duplicate metadata receives ranks 1..N;
normal distinct source positions each have rank 1. All TYPE_CHECKING imports remain present.

## Diagnostics and incomplete graphs

Unresolved or ambiguous imports live in diagnostics with their full import records and ranks,
not fake target nodes. Stable codes cover ambiguous module ownership/imports, invalid importer,
unresolved relative imports and beyond-root imports. Partial snapshots add `incomplete_source_snapshot`.
All diagnostics use fixed source-free messages and safe relative locations. Any diagnostic or partial
input makes the summary partial. Structural validation errors such as conflicting identity,
unsupported snapshot version and invalid reference fail construction rather than persist an invalid
graph. Untrusted decoding rejects errors, unknown fields and unsupported versions without repair.

## Queries and complexity

`QueryRepositoryGraph` indexes nodes and edge adjacency once. Node lookup is expected O(1).
Neighbors, dependencies and reverse dependencies deduplicate node IDs and return lexical order;
import edges themselves retain multiplicity. Reverse dependencies require an internal module.
Shortest directed paths use BFS with lexical neighbor tie-breaking, returning null when disconnected
and a singleton for start=end. A kind filter restricts traversal when supplied.

Iterative Kosaraju computes SCCs of internal import edges; external nodes are excluded. A singleton
is cyclic only with a self-loop. Components and their members are lexically sorted.
`type_checking_only` means the full cyclic component contains no runtime cycle after removing all
TYPE_CHECKING edges. Mixed components with any runtime cycle are false. `--runtime-only` reports
only the filtered cycles. This syntax flag is not a guarantee of actual runtime execution.
Cycles are structural findings, never architecture violations.

Construction and validation use indexed ownership and per-file symbol stacks, then canonical sorts:
roughly O((V+E) log(V+E)) plus metadata serialization. Indexed BFS/SCC traversal is O(V+E) before
lexical sorting; sorting adds up to O((V+E) log(V+E)). Memory is O(V+E) plus serialized artifact size.
`scripts/benchmark_repository_graph.py` prepares 500 files/modules, 2,000 symbols and 1,000 imports,
then times only graph construction and validation. It reports size/counts with no CI timing threshold.
This engineering measurement is not a repair experiment.

## Safety and limitations

Shared artifact I/O uses bounded regular-file reads (64 MiB), symlink rejection, same-directory
atomic replacement, fsync and temporary cleanup. Graph output cannot replace its input snapshot,
including resolved aliases and hard links. `--protected-root` prevents writes within a known source
repository. Snapshots deliberately contain no checkout root, so callers must pass context when
known. Stable trusted output parents remain required; this is not an adversarial concurrent filesystem
sandbox. No source text, host metadata, absolute paths or timestamps enter canonical graphs.

Snapshot identity is provenance, not a signature: a graph read without its snapshot cannot independently
prove that a maliciously recomputed artifact matches the original source. Retain both artifact hashes
in experiment records. Snapshot ordering is already validated; shuffled inputs are rejected upstream.
Static syntax cannot resolve dynamic imports, re-exports, import hooks or runtime conditions. No
architecture inference, constraints, LLMs, agents, repair, HTTP graph API or visualization is included.

See [schema](../schemas/repository-graph-v1.md) and [ADR-0004](decisions/ADR-0004-canonical-repository-graph.md).
