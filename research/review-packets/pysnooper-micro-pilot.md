# PySnooper architecture-profile review packet

Status: `REVIEW_REQUIRED`. This packet is source-free and is not a human approval. Validated Phase
12.8B graph evidence has been imported; the profile decision remains `PENDING`.

- Project/task: PySnooper / BugsInPy `PySnooper-2`
- Buggy revision: `e21a31162f4c54be693d8ca8260e42393b39abd3`
- Draft profile fingerprint: `e2694d6a8016382036a3670476d75a0ca16d7f9872678156d16fba6de0f441f1`
- Graph evidence fingerprint: `e08af7f18e793a17e06721127ebf43d791c299a92702dba5c06d932ab527ab1e`
- Canonical graph fingerprint: `b1c318faba70d50225ceba74254edb18727013291de8607695334f8f0a98802c`
- Acquisition fingerprint: `b5820205e5339b0a64a7efdfef6bd74cb71b90d58a18f90fa9847af4123f4c1f`
- Project license: PySnooper is `VERIFIED` as MIT at the buggy revision. BugsInPy and the SWE-bench
  Verified dataset remain `UNRESOLVED`, so benchmark redistribution remains `UNRESOLVED`.
- Components/selectors: public API (two exact modules), tracing (one), representation (one), support (two), tests (prefix).
- Rules/rationale: support is independent; representation may use support; tracing may use representation/support; public API delegates inward; production components are acyclic. These encode the proposed inward dependency direction and require human confirmation.
- Supporting graph facts: 14 modules; 12 assigned; 2 unassigned; 0 ambiguous; 19 internal and 43
  external dependency edges; 14 SCCs; 0 cycles. Five rules were enabled, four evaluated, one skipped,
  and no violation was reported. The report is `partial=true` and `passed=false`.
- Unassigned modules: `setup` and `misc.generate_authors`. These names are derived deterministically
  from the [immutable upstream tree metadata](https://github.com/cool-RR/PySnooper/tree/e21a31162f4c54be693d8ca8260e42393b39abd3)
  using the analyzer's module-name rules. Both lie outside the current `pysnooper` and `tests`
  selectors; no source content was imported.
- Skipped rule: `production-components-acyclic`, reason `incomplete_assignments`. Cycle evaluation
  fails closed whenever any module lacks exactly one component assignment; this is why the zero-cycle
  graph summary does not make the profile report pass.
- Proposed amendment, not applied: add a `project-tooling` component with exact selectors for `setup`
  and `misc.generate_authors`. Existing dependency rules would remain unchanged and production cycle
  scope would still exclude tooling. If accepted, compile a new profile fingerprint and rerun graph
  evaluation before approval; do not reuse this pending decision against a changed fingerprint.
- Limitations: static Python imports only; dynamic imports/runtime dependencies may be missed; tests are not architectural ground truth; no claim of representativeness.

Reviewer choice (select exactly one manually): **APPROVE CURRENT PROFILE** only with an explicit
justification for leaving two error-policy modules unassigned; **AMEND** by adopting or revising the
proposed tooling component and requiring regenerated evidence; or **REJECT** with requested changes.
Then complete every checklist item and edit `research/reviews/pysnooper-profile-decision.json`
manually. Do not approve solely because the graph has zero reported violations: one rule was skipped.
