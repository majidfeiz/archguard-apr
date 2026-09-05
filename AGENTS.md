# Contributor instructions

Inspect the repository, hidden files and git status before editing. Preserve user work.
Respect entrypoints → application → domain. Domain and application must remain vendor-neutral;
application imports only domain and the standard library. Keep business logic out of adapters.
Add meaningful behavior tests, validate configuration and maintain deterministic experiments.
Never fabricate citations, datasets, metrics or results. Prevent gold-patch and hidden-answer
leakage. Never commit secrets, model outputs or generated benchmark data. Record seeds,
versions, configurations and provenance. Document architectural decisions in ADRs.
Run all checks in README, review the diff and use scoped conventional commits.
Phase 3 permits read-only AST analysis, immutable repository graphs and structural queries.
Never import, execute or modify target source. Keep analysis separate from persistence behind ports.
Maintain source-free diagnostics, stable IDs/hashes and byte-identical artifacts across locations.
Output must remain outside analyzed roots. Add immutability and determinism tests for changes.
Build graphs only from validated snapshots; never reread source in graph construction.
No architecture inference, constraint engine, repair execution or agent integration belongs here.
The complete test suite must retain at least 90% combined statement and branch coverage.
