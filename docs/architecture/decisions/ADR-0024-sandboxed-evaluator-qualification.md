# ADR-0024: Sandboxed evaluator qualification

Status: Accepted for Phase 12.8F implementation.

## Context

Outcome-blind candidates require reproducibility qualification without exposing target source, fixed
code, reference material, or raw logs to ArchGuard artifacts. Legacy evaluators may also fail for
scientifically meaningful environment reasons rather than engineering defects.

## Decision

Use immutable, fingerprinted task adapters that bind exact revisions, official repositories,
dependency metadata hashes, exact constraints, selectors, license identities, and one common sandbox
contract. Build dependencies only inside isolated containers during a controlled network phase. Run
three buggy attempts and one fixed control in fresh non-root, network-disabled, resource-limited
containers. Retain only normalized counts, categories, durations, hashes, and resource facts.

Classification is pure domain logic. Acquisition/execution is a GitHub-runner script, while canonical
packaging and hostile ZIP validation remain infrastructure. Imported evidence is append-only and
cannot replace conflicting prior evidence.

## Consequences

Non-STABLE results remain valid scientific evidence and do not fail the workflow. Only STABLE results
with passing fixed controls qualify. A prior-result conflict requires human review. Implementation
alone changes no qualification count, freezes no task list, and cannot assert Phase 13 readiness.
