# PySnooper architecture-profile review packet

Status: `FROZEN`. This source-free packet records the user-authorized human `APPROVE` decision for
the amended PySnooper profile. It is not protocol, benchmark-population, or Phase 13 approval.

- Project/task: PySnooper / BugsInPy `PySnooper-2`
- Buggy revision: `e21a31162f4c54be693d8ca8260e42393b39abd3`
- Draft profile fingerprint: `e2694d6a8016382036a3670476d75a0ca16d7f9872678156d16fba6de0f441f1`
- Graph evidence fingerprint: `e08af7f18e793a17e06721127ebf43d791c299a92702dba5c06d932ab527ab1e`
- Proposed amended profile: `950cd9889d5d4335e60b7429d2feddf2230db42654e5ec844edd813596b6d6d7`
- Amendment: exact selectors for `setup` and `misc.generate_authors` in `project-tooling` only;
  production assignments and rules are unchanged and production-only rules exclude this component.
- Local macOS/ARM engineering result: 14/14 assigned, 0 ambiguous, all 5 rules evaluated, 0 skipped,
  0 violations, `passed=true`, with two byte-identical outputs. This is not Linux x86 qualification.
- Linux x86 run `37433179494` evidence is imported with fingerprint
  `2eb422f3a48222aca7f664537f0fad41441a1841886b3a61280af00e50a9639c`; all 14 modules were assigned,
  all 5 rules evaluated, and the non-partial result passed with zero violations.
- The approved/frozen profile fingerprint is
  `950cd9889d5d4335e60b7429d2feddf2230db42654e5ec844edd813596b6d6d7`. The earlier AMEND decision
  remains preserved in `research/reviews/pysnooper-profile-amend-decision.json`.
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
- Historical Phase 12.8B context: the original profile left `setup` and `misc.generate_authors`
  unassigned, causing one incomplete-assignment skip. The later exact tooling amendment and new Linux
  x86 evidence supersede that pending review state without rewriting its evidence.
- Limitations: static Python imports only; dynamic imports/runtime dependencies may be missed; tests are not architectural ground truth; no claim of representativeness.

The final approval applies only to the amended profile and complete Linux x86 evaluation. It does not
retroactively approve the incomplete Phase 12.8B profile.
