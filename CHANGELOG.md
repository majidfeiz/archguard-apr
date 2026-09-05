# Changelog

## 0.2.0

Read-only deterministic Python discovery and AST snapshots; canonical artifact writer/reader;
repository analyze/inspect CLI; typed analysis options; safety, consistency and determinism tests;
synthetic examples and a 500-file engineering guardrail. No graph or repair execution.
Breaking: RepositoryAnalyzerPort now accepts AnalysisOptions and returns RepositorySnapshot.
ArtifactReference gains an optional SHA-256. Full-suite coverage threshold increases to 90%.


## 0.1.0

Initial agent-agnostic foundation, metadata CLI, health API, research protocol and quality gates.
No repair execution or agent integrations are implemented.
