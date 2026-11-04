# V2.1B verification

- Baseline: `b133388555b3c38cf2bac520d712020a5299ba3a`
- Branch: `phase/v2-01b-pysnooper2-tree-identity`
- Provider calls: 0
- Scientific executions: 0
- External Git acquisitions: 0

Both prerequisite commits are ancestors of the clean merged baseline. PySnooper-2 remains blocked
only by `PYSNOOPER_2_FIXED_TREE_IDENTITY_RECHECK_REQUIRED`; PySnooper-3 remains ready. Historical
Phase 13 evidence is unchanged. No real imported identity file is created in this phase.

The implementation adds a manual identity-only workflow, immutable source-free evidence contract,
strict bounded archive validation, idempotent import, canonical archive builder, CLI commands,
schema/run documentation, and synthetic author-owned security fixtures. Final test counts and
coverage are reported in the completion handoff.

Python 3.12.13 verification selected 1,045 non-Docker tests: 1,044 passed, one was skipped, and
three Docker tests were deselected. Combined statement and branch coverage was 90.11%. The focused
V2/archive/patch/architecture run passed 111 tests. Ruff format and lint, strict mypy, workflow YAML
parsing, canonical synthetic archive regeneration, leakage checks, and CLI validate/import tests
passed. Python 3.13.13 was available entirely offline in an isolated environment and produced the
same full-suite result and 90.11% coverage.
