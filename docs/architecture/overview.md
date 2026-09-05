# Architecture contract

The modular monolith follows entrypoints → application → domain. Domain uses only the Python
standard library. Application defines Protocol ports and imports only domain and standard-library
types. Infrastructure may depend on application and domain. Entrypoints compose these layers;
schemas validate boundary data and may import domain, never the reverse.

No configuration, logging or framework objects enter domain values. Frozen dataclasses provide
internal values; Pydantic validates boundaries. Repository analysis returns an immutable canonical snapshot; separate writer/reader ports handle
artifacts. Architecture-profile/candidate outputs retain artifact references until later design.
The local analyzer implements read-only discovery and AST parsing; execution remains unimplemented. Warning-only validation passes.
`AnalyzeRepository` and `InspectRepository` orchestrate ports in application services.

AST tests resolve absolute and relative imports and reject dynamic loading in core. Core imports
of application outer layers, FastAPI, Typer, MCP, Codex, Claude or vendor SDKs must fail.
Imports perform no I/O, handler installation or service startup. Factory calls load settings.

See [repository analysis](repository-analysis.md) and ADR-0003 for the Phase 2 contract.
