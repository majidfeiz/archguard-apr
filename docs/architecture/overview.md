# Architecture contract

The modular monolith follows entrypoints → application → domain. Domain uses only the Python
standard library. Application defines Protocol ports and imports only domain and standard-library
types. Infrastructure may depend on application and domain. Entrypoints compose these layers;
schemas validate boundary data and may import domain, never the reverse.

No configuration, logging or framework objects enter domain values. Frozen dataclasses provide
internal values; Pydantic validates boundaries. Analysis/profile/candidate outputs use artifact
references to avoid premature graph/patch schemas. Contracts require read-only analysis and
future execution isolation; no production implementation exists. Warning-only validation passes.
Future use cases belong in application services; no empty service classes are created.

AST tests resolve absolute and relative imports and reject dynamic loading in core. Core imports
of application outer layers, FastAPI, Typer, MCP, Codex, Claude or vendor SDKs must fail.
Imports perform no I/O, handler installation or service startup. Factory calls load settings.
