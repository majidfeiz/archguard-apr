# Phase 9 verification

Baseline: `989e38f6fae041d803140d85c767603dc6216ae3` on clean `main`, version 0.8.0.
Baseline suite: 486 passed, 3 Docker tests skipped, combined statement/branch coverage 93.43%.

Official provider documentation was accessed 2026-10-01 before implementation; URLs are recorded in
`docs/providers/provider-compatibility.md`. Final command results and artifact hashes are recorded only
after they are actually executed. Live tests are optional and are not represented as executed without
credentials and explicit cost acknowledgement.

## Verified results

- Python 3.12: 508 passed, 3 skipped (Docker-marked), 2 dependency deprecation warnings.
- Python 3.13: 508 passed, 3 skipped (Docker-marked), 2 dependency deprecation warnings.
- Statement coverage: 93.77%; branch coverage: 85.66%; combined coverage: 92.37%.
- Focused provider/configuration/security CLI tests: 22 passed.
- Ruff format/lint, strict mypy, pre-commit, lock check and package build: passed.
- Self-architecture: passed, zero violations across seven enabled rules.
- Phase 7 Docker isolation: 3 passed against pinned image
  `sha256:e4aea41738c84d8467103043606d66e62e453429331a9922e2b9aca7672d5979`.
- Phase 9 application image: built as `archguard-apr:phase-9`.
- Offline orchestration demonstration: passed twice; byte-identical output and zero replay calls.
- Deterministic hashes: checkpoint `d00ecb81d58626ea2b4b1287abfb4921846b4d4ccbcb3c3ed857928b0d405f64`,
  events `a41e65488982a1abc2bebf62bc053eb9cf9c00efa02bea137049950ea351a179`, spec
  `d50ae5cc34362bf1d4aa6cce54bdbb8adc2e9a48eae0d967cffc8321b56267f7`.
- Secret-pattern scan: only intentional recognizable fake-secret security fixtures matched.
- Orphans: one expected primary Git worktree; no `archguard-*` containers remained.
- Live OpenAI: Not executed — credentials/cost acknowledgement not provided.
- Live Anthropic: Not executed — credentials/cost acknowledgement not provided.
- GitHub Actions: not executed locally; workflow configuration was updated and validated as YAML.
