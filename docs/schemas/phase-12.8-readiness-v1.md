# Phase 12.8 source-free schemas

`archguard.phase-12.7-x86-qualification-import/v1` records only immutable revisions, normalized failure
signatures, platform, evaluator/profile/cleanup conclusions, provenance URLs, the ZIP hash, and a
timestamp/path-independent fingerprint. It contains no source, patch, gold material, or raw log.

`archguard.human-decision/v1` requires a subject kind, exact reviewed fingerprint, reviewer name,
timestamp, `PENDING|APPROVE|REQUEST_CHANGES|REJECT`, explicit checklist booleans, and comments. Pending
templates leave identity/time blank and all checks false.

`archguard.phase-13-readiness/v1` contains factual gate booleans, stable blocker codes, a derived
`phase_13_ready` boolean, and a deterministic fingerprint. No manual readiness field is accepted.
