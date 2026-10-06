# Phase 12.8C verification

Baseline: clean local `main` at `cf6e8feb5357766acc84fa1f39615e97c8bf72ed`, version `0.12.8`.
Phase 12.8B run `37152285061`, graph `e08af7f18e793a17e06721127ebf43d791c299a92702dba5c06d932ab527ab1e`,
and old profile `e2694d6a8016382036a3670476d75a0ca16d7f9872678156d16fba6de0f441f1`
were verified.

The user-authorized human decision is `AMEND`, not approval, and is strictly bound to Phase 12.8B.
The protocol decision is unchanged. Proposed profile fingerprint
`950cd9889d5d4335e60b7429d2feddf2230db42654e5ec844edd813596b6d6d7` adds only exact selectors
`setup` and `misc.generate_authors` under `project-tooling`; production assignments/rules are unchanged.

Local engineering execution used only buggy revision `e21a31162f4c54be693d8ca8260e42393b39abd3`.
Two independent passes produced byte-identical evidence SHA-256
`f360d53b815e5960cd516cec5f7dd3d71348d4649f946194bd326d9bbe6958de` and canonical graph
`b1c318faba70d50225ceba74254edb18727013291de8607695334f8f0a98802c`. Actual result: 14 modules,
14 assigned, 0 unassigned, 0 ambiguous, 5 rules evaluated, 0 skipped, 0 violations, `passed=true`.
This macOS/ARM output is engineering evidence only and is not committed generated evidence.

The manual workflow uses native `ubuntu-24.04`, bounded resources, runtime `RUNNER_TEMP`, strict
cleanup/leakage checks, and one exact-allowlist Artifact retained 14 days. Linux x86 import and final
human approval remain pending. `architecture_analysis_complete=false`, `profile_approved=false`,
`profile_frozen=false`, and `phase_13_ready=false`; `ARCHITECTURE_ANALYSIS_INCOMPLETE` and
`PROFILE_REVIEW_REQUIRED` remain blockers.

Verification completed with 686 passing tests and 3 Docker-dependent skips under Python 3.12,
90.07% combined statement/branch coverage, and 683 passing tests with the same 3 skips under Python
3.13. Ruff format/lint, strict mypy, pre-commit, frozen lock validation, package sdist/wheel build,
workflow YAML parsing, and self-architecture validation passed. `actionlint` and `shellcheck` were not
installed locally; the workflow syntax and shell are additionally exercised by the manual GitHub run.
