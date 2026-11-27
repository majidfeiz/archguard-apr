# ADR-0029: Bounded V2 micro-pilot runner

## Status

Accepted for V2.2 implementation. Scientific execution remains separately human-authorized.

## Decision

The micro-pilot is an eight-ordinal, sequential application workflow. Its domain state contains
only frozen identities, stage outcomes, token/cost accounting, terminal classifications and
source-free diagnostic fingerprints. Provider, repository, evaluator, checkpoint and cleanup
effects remain behind application ports.

The protocol loader binds the canonical task order, condition order, model snapshot, response
schema, pricing, task manifests, readiness, token limits, retry count and all cost ceilings to
reviewed fingerprints. Any drift fails before source acquisition or provider access.

Every call is admitted by reserving USD 0.1175. Reconciliation uses reported usage and the
frozen standard-input/output prices, without assuming a cached-input discount, and releases the
reservation into observed cost. The ledger rejects gaps, duplicates,
contradictory resume state, a ninth ordinal, more than USD 0.9400 total reservations, or an
observed-plus-reserved amount above USD 1.0000. There is no retry or parallel-call path.

The infrastructure adapter acquires only manifest-bound revisions, disables hooks, LFS smudge
and recursive submodules, and verifies commit/tree identities before reading source. Symlinks
and gitlinks are rejected. Fixed evaluator material never enters provider-visible context.
Candidate execution is delegated to the existing bounded, network-disabled evaluator process.

Checkpoints are canonical and atomically replaced after every charged call. Resume continues at
the first missing ordinal. Evidence is restricted to a flat allowlist of source-free JSON,
checksums and a deterministic ZIP; prompts, source, patch bodies, provider responses, raw logs,
gold material, secrets and environment dumps are rejected.

## Consequences

Real execution is available only through the exact CLI authorization phrase and the protected
GitHub environment gate. Offline protocol validation and the deterministic fake-provider run
exercise orchestration and evidence production without network or scientific execution. Partial
workflow failure retains enough source-free state to resume without repeating completed calls.
