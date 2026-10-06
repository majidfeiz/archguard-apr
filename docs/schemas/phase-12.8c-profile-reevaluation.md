# Phase 12.8C profile re-evaluation evidence

The source-free archive contains exactly `manifest.json`, `amended-profile-summary.json`,
`graph-evidence.json`, `constraint-evaluation.json`, `determinism.json`,
`security-scan-summary.json`, `cleanup-summary.json`, `readiness-summary.json`, and `SHA256SUMS`.
Each JSON record is canonical, schema-bound, and fingerprinted.

Validation rejects extra, missing, duplicate, nested, traversal, symlink, oversized, noncanonical, or
incorrectly hashed members. It binds `PySnooper-2`, the immutable buggy revision, amended profile,
graph identity, complete/unambiguous assignment, zero incomplete-assignment skips, two byte-identical
runs, cleanup, and false readiness. Source, patches, raw logs, gold, secrets, and host paths are
forbidden. Linux x86 evidence still requires import and human review.
