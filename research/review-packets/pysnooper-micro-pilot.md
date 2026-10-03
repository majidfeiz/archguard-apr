# PySnooper architecture-profile review packet

Status: `REVIEW_REQUIRED`. This packet is source-free and is not a human approval.

- Project/task: PySnooper / BugsInPy `PySnooper-2`
- Buggy revision: `e21a31162f4c54be693d8ca8260e42393b39abd3`
- Draft profile fingerprint: `e2694d6a8016382036a3670476d75a0ca16d7f9872678156d16fba6de0f441f1`
- Project license: license file was observed in Phase 12.7, but its identifier and redistribution audit remain unresolved; do not approve until independently verified.
- Components/selectors: public API (two exact modules), tracing (one), representation (one), support (two), tests (prefix).
- Rules/rationale: support is independent; representation may use support; tracing may use representation/support; public API delegates inward; production components are acyclic. These encode the proposed inward dependency direction and require human confirmation.
- Supporting graph facts: not imported. Phase 12.7 established profile compilation determinism only; deterministic buggy-revision analysis remains required.
- Unassigned/ambiguous policy: both are errors. Actual unassigned/ambiguous modules are unknown until validated snapshot analysis.
- Limitations: static Python imports only; dynamic imports/runtime dependencies may be missed; tests are not architectural ground truth; no claim of representativeness.

Reviewer checklist: verify revision/license evidence, inspect each component selector, validate every rule and rationale against source-free graph facts, resolve unassigned/ambiguous modules, acknowledge limitations, confirm no fixed/gold material informed the profile, then edit `research/reviews/pysnooper-profile-decision.json` manually.
