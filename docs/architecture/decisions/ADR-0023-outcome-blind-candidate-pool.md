# ADR-0023: Outcome-blind licensed candidate preparation

Status: Accepted for Phase 12.8E.

## Context

Pilot preparation needs multiple upstream projects without treating repository visibility, framework
licensing, or later repair behavior as task eligibility. Source and hidden answers must remain outside
tracked research records and ordinary agent context.

## Decision

Represent framework, dataset, and project licensing as independent immutable evidence records. An
absent or ambiguous official license stays unresolved. Admit a candidate only from source-free,
pre-repair metadata bound to exact commits, a verified project license, an evaluator locator, and
bounded platform/resource properties. Reject gitlink/LFS dependencies. Select by stable task ID using
project round-robin with a cap of four, and fingerprint both the canonical input and policy before
selection. Keep this preparation pool distinct from qualification and final pilot freeze.

The pure policy and records live in the domain. Canonical JSON loading and persistence validation stay
in infrastructure. Neither layer acquires repositories, executes evaluators, or reads target source.

## Consequences

Selection is reproducible and cannot be revised because a repair later succeeds or fails. Framework
or dataset uncertainty remains visible without contaminating verified upstream-project conclusions.
Phase 12.8E may establish pool sufficiency, but cannot qualify tasks, freeze the pilot, approve the
protocol, resolve all licensing, or assert Phase 13 readiness.
