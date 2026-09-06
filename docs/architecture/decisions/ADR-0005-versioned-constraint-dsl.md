# ADR-0005: Versioned explicit constraint DSL and deterministic conformance

Status: Implemented for Phase 4; pending pull-request review.

## Context

Phase 3 provides validated immutable syntax graphs. Explicit reproducible architectural acceptance
requires independently versioned user-authored specifications and reports. Phase 1's analyzer and
before/after validator contracts prematurely mixed paths, profile artifacts and candidate execution.

## Decision

Remove ArchitectureAnalyzerPort and ArchitectureValidatorPort. Introduce separate
ArchitectureProfileLoaderPort, ArchitectureProfileReaderPort, ArchitectureProfileWriterPort,
ArchitectureConstraintEvaluatorPort, ArchitectureReportReaderPort and ArchitectureReportWriterPort.
The evaluator consumes a graph and immutable profile, returns an immutable report and never reads source.
Before/after validation is reserved for Phase 5, without implementing a placeholder now.

Use independently versioned profile/report schema strings `"1"`. Components are explicit selector
families, with exact/prefix module/path boundaries. IDs determine canonical order; declaration order
is irrelevant. Four typed rules cover forbidden internal dependencies, complete internal allow lists,
forbidden textual external imports and scoped import cycles. Extract the Phase 3 iterative SCC utility
into domain and reuse it for both query and report/evaluation validation.

Never resolve ambiguous assignment by order. Assignment policy controls diagnostic severity; missing
membership conservatively skips affected rules. All ambiguity, skipped rules and partial graph input
make reports partial. All external rules skip on collapsed top-level external names. CLI writes valid
partial reports but defaults to exit 4; explicit allow-partial only changes exit policy.

Aggregate dependency violations per rule/source/target, preserving occurrences; aggregate cycles per
rule/cyclic SCC. Hash canonical profile semantics, full report data and canonically framed violation
evidence with SHA-256. Include disabled rules; exclude host, time, destinations and YAML formatting.
Embed the canonical profile and used import edges in reports for standalone invariant checks.
Retain source-free messages and evidence, bounded strict decoding and independent atomic persistence.

## Consequences

The port removal is an intentional breaking 0.x change. Profiles are reviewable specifications, not
inferred truth. Granularity avoids repeated imports inflating violation counts, but independent rules
can each flag the same dependency. Conservative skipping may sacrifice findings to make incompleteness
explicit. Embedded evidence/profile increases artifact size but allows deterministic validation without
source reads. Hashes establish internal consistency, not authenticity of a maliciously rehashed report.
Self-hosting CI and a fixed engineering workload provide development guardrails, not research results.
No inference, patch comparison, repair, model, agent or integration is introduced.
