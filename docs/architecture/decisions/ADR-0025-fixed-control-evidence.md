# ADR-0025: Fixed-control evidence is separate from scientific classification

## Status

Accepted for Phase 12.8F.2.

## Decision

Buggy repetitions and fixed-control execution remain separate evidence. A scientific classification is
available only after three valid, stable buggy evaluator runs and a zero-exit fixed run in the identical
dependency environment. A failed fixed control produces `FIXED_CONTROL_FAILED` or
`FIXED_CONTROL_INFRASTRUCTURE_FAILURE`, `NOT_QUALIFIED`, and mandatory review; it is not inferred to be
`ENVIRONMENT_SENSITIVE`.

Fixed evidence records an enum stage, bounded outcome/count/duration data, normalized class and hashes,
selector and dependency-environment fingerprints, image identity, and optional infrastructure category.
Raw output, source, test contents, patches and environment dumps remain prohibited.

## Consequences

Run 37672954475 remains diagnostic historical evidence and is not qualification evidence. Adapter v2
identities remain unchanged because its source-free artifact proves no adapter amendment. A new Batch-A
run is required to identify the failure stages before any reviewed adapter correction.
