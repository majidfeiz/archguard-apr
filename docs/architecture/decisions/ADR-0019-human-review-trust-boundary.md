# ADR-0019: Human-review trust boundary

Status: Accepted for Phase 12.8.

Automated code may prepare source-free review packets, calculate fingerprints, and validate a decision
file. It cannot author a reviewer identity or convert `PENDING` into approval. An approval is effective
only when every checklist answer is true and its reviewed fingerprint equals the current artifact.
Changing the artifact makes the decision stale. Frozen profiles are derived from valid decisions; there
is no override flag. This keeps review authority outside automated agents and prevents fake approvals.
