# ADR-0015: Evidence-gated iterative repair

Status: accepted (2026-10-01).

Represent repair search as immutable provider-neutral tasks, candidates, feedback, lineage, validation
evidence and final results. Use complete baseline-relative replacement patches, deterministic prechecks,
mandatory Phase 5/4/7 gates and evidence-only ranking. This makes replay and deduplication tractable and
prevents provider claims from becoming evidence. The tradeoff is conservative rejection and no claim
of semantic patch equivalence.
