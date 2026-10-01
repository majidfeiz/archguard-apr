# ADR 0018: Evidence-gated external benchmark readiness

Status: accepted for Phase 12.5.

Readiness is derived from immutable per-gate evidence, never assigned from a status string. Network and
filesystem adapters remain outside core policy. External storage is resolved outside Git and separated
into public, evaluator and gold zones. Profile freezing requires an exact human review artifact. This
prevents CI success or automated prose from masquerading as research readiness, at the cost of keeping
Phase 13 blocked until external evidence and human judgment exist.
