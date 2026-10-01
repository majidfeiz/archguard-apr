# Architecture-profile review guide

Codex may create only `DRAFT` or `REVIEW_REQUIRED` profiles from documented structure, package layout,
actual dependencies and test/production boundaries. Each rule records scope, rationale, evidence,
confidence, ambiguity and affected modules. The package must show component/dependency summaries,
baseline violations, ambiguous assignments and approve/revise/reject fields without gold information.

A human decision uses `archguard.architecture-profile-review/v1` and binds the exact fingerprint,
reviewer identity/date, comments, approved/rejected rules and requested changes. Stale/wrong-profile and
partial approvals cannot freeze a profile. No profiles were drafted because no real task/project passed
qualification; human-reviewed and frozen counts are zero.
