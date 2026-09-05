# ADR-0003: Canonical repository snapshots

Status: Accepted for Phase 2.

Context: Reproducibility needs location-independent structural artifacts and independent analysis
and persistence. The Phase 1 analyzer returning an artifact reference coupled these responsibilities.

Decision: Evolve RepositoryAnalyzerPort to return an immutable RepositorySnapshot with AnalysisOptions.
Add writer/reader ports and application orchestration. Use standard-library AST, descriptor-relative
Unix traversal, byte hashing and deterministic JSON framing. Use the existing Pydantic dependency
only to decode untrusted boundary data. No runtime dependency is added. Parse a fixed Python 3.12
grammar on supported Python 3.12/3.13 interpreters. Retain failed/skipped records and safe diagnostics.

Consequences: The placeholder analyzer contract changes at 0.2.0. ArtifactReference gains an optional
SHA-256. Symlinks are skipped or rejected, never followed. Unsafe platforms fail closed. Output must
be outside target roots. Canonical records exclude source, time and host identity. Partial fingerprints
cannot identify unread content. Inspect validates consistency but cannot prove AST truth or authorship.
Source roots are explicit; no graph, package resolution, architecture inference or HTTP analysis exists.
Hostile concurrent mutations/resource isolation remain outside the Phase 2 threat model.
