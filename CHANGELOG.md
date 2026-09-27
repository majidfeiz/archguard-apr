# Changelog

## 0.8.0

- Add typed provider-neutral roles, capabilities, run/candidate state machines and bounded budgets.
- Add canonical hash-chained events, checkpoints, verified resume and side-effect-free replay.
- Add evidence-only deterministic ranking, explicit human decisions, scripted agents and repair CLI.

## 0.7.0

- Add immutable digest-pinned execution plans and fail-closed Docker execution.
- Add source-free command/JUnit evidence, functional deltas and combined validation gates.
- Add execution CLI, isolation tests, schema/threat-model documentation and Docker CI coverage.

## 0.6.0

- Add deterministic compiled retrieval queries, graph seed discovery, bounded expansion,
  explainable integer scoring, stable ranking and exact byte/line budget decisions.
- Add source-free retrieval manifests and separately classified sensitive context bundles with
  snapshot-bound, descriptor-relative source reads.
- Add independently labeled offline MRR, Hit@K, Recall@K and Precision@K evaluation.
- Add the `archguard context` CLI, adversarial tests, examples, ADRs and research traceability.

## 0.5.0

- Add bounded exact-byte unified-diff inspection with stable rejection diagnostics.
- Add detached Git worktree validation with repository-state proofs and unconditional cleanup.
- Add semantic before/after architecture deltas and canonical validation artifacts.
- Add `archguard patch` inspection, validation, result, delta, and violation commands.

## 0.4.0

- Add explicit ArchitectureProfile v1 DSL, deterministic assignment and four typed conformance rules.
- Add ArchitectureReport v1 with aggregated source-free evidence, stable violation IDs,
  canonical profile/report fingerprints, strict bounded YAML/JSON adapters and atomic persistence.
- Add architecture CLI, compliant/violating examples, self-hosting CI and engineering workload.
- Breaking ports: remove ArchitectureAnalyzerPort and ArchitectureValidatorPort; replace with
  separate profile loader/reader/writer, constraint evaluator and report reader/writer contracts.
  Before/after candidate validation is reserved for Phase 5 (ADR-0005).
- Share Phase 3 SCC implementation with constraint evaluation. No inference, patch comparison,
  repair, LLM, agent or product integration was added.


## 0.3.0

- Add immutable canonical repository graph v1 with conservative static import resolution.
- Preserve import occurrences, partial diagnostics and deterministic content identity.
- Add graph artifact ports, safe persistence, structural queries and graph CLI.
- Add graph tests, CI smoke commands, engineering guardrail and schema/ADR documentation.
- No architecture inference, constraints, execution or LLM integration.

## 0.2.0

Read-only deterministic Python discovery and AST snapshots; canonical artifact writer/reader;
repository analyze/inspect CLI; typed analysis options; safety, consistency and determinism tests;
synthetic examples and a 500-file engineering guardrail. No graph or repair execution.
Breaking: RepositoryAnalyzerPort now accepts AnalysisOptions and returns RepositorySnapshot.
ArtifactReference gains an optional SHA-256. Full-suite coverage threshold increases to 90%.


## 0.1.0

Initial agent-agnostic foundation, metadata CLI, health API, research protocol and quality gates.
No repair execution or agent integrations are implemented.
