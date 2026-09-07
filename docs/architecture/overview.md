# Architecture contract

The modular monolith follows entrypoints → application → domain. Domain uses only the Python
standard library. Application defines Protocol ports and imports only domain and standard-library
types. Infrastructure may depend on application and domain. Entrypoints compose these layers;
schemas validate boundary data and may import domain, never the reverse.

No configuration, logging or framework objects enter domain values. Frozen dataclasses provide
internal values; Pydantic validates boundaries. Repository analysis returns an immutable canonical snapshot; separate writer/reader ports handle
artifacts. Architecture profiles and reports are immutable versioned values; candidate outputs remain future work.
The local analyzer implements read-only discovery and AST parsing; execution remains unimplemented. Warning-only validation passes.
`AnalyzeRepository` and `InspectRepository` orchestrate ports in application services.

AST tests resolve absolute and relative imports and reject dynamic loading in core. Core imports
of application outer layers, FastAPI, Typer, MCP, Codex, Claude or vendor SDKs must fail.
Imports perform no I/O, handler installation or service startup. Factory calls load settings.

See [repository analysis](repository-analysis.md) and ADR-0003 for the Phase 2 contract.

Phase 3 adds pure `DeterministicGraphBuilder`, `BuildRepositoryGraph`, `InspectRepositoryGraph` and
`QueryRepositoryGraph`. Separate graph ports isolate artifact I/O. See [graph architecture](repository-graph.md).

Phase 4 adds pure explicit component assignment and `DeterministicConstraintEvaluator` over validated
graphs. Separate profile loader/reader/writer and report reader/writer ports isolate boundaries;
CLI composes compilation and evaluation services. The domain SCC utility is shared with graph
queries. See [constraint engine](constraint-engine.md), [DSL](constraint-dsl.md) and ADR-0005.
No automatic architecture inference is implemented.
Phase 5 adds a patch-validation application workflow. Infrastructure alone reads exact patch bytes,
runs bounded Git commands, and manages temporary worktrees; application orchestrates existing
analysis/graph/evaluation ports; domain values classify semantic architecture deltas.
