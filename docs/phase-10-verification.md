# Phase 10 verification

Baseline: `498d720971669b0753a030c937c27afc9cdf64b2` on clean `main`, version 0.9.0.
Baseline: 508 passed, 3 Docker-marked skipped; combined coverage 92.37%.

Final command results, coverage, integrity evidence and hashes are recorded only after execution.
Optional live demonstration: Not executed — credentials/cost acknowledgement not provided.

## Verified results

- Python 3.12: 535 passed, 3 Docker-marked skipped, 2 dependency deprecation warnings.
- Python 3.13: 535 passed, 3 Docker-marked skipped, 2 dependency deprecation warnings.
- Phase 10 focused task/patch/security/lineage/loop/ranking tests: 27 passed.
- Combined Phase 8–10 focused regressions: 66 passed.
- Statement coverage: 93.25%; branch coverage: 83.95%; combined coverage: 91.64%.
- Ruff, strict mypy, pre-commit, lock/frozen sync, package build, doctor and Compose: passed.
- Self-architecture: passed with zero violations across seven enabled rules.
- Phase 7 Docker isolation: 3 passed against pinned validation image
  `sha256:e4aea41738c84d8467103043606d66e62e453429331a9922e2b9aca7672d5979`.
- Phase 10 image: `archguard-apr:phase-10`, image
  `sha256:729da5a935a297b48982e1afc2cf685c4a8aca394697fc370c3343f647cfe7b3`.
- Offline demonstration: passed twice with byte-identical artifacts and zero provider calls.
- Task `9f880aed7dfb925e7bfeb6fdad9e2b138136c61d44a2724c90c83fcfe82896fa`;
  candidates A/B/C `6ff4f077c7ed922ce784ed0e4223ae5cec846f88f795e5c9310255588f3fc0f7`,
  `14f818e162a0d3403cb654bbb594aef9a06f8052ee6f1d1e3e3a6a9116c7aeaa`,
  `554f40ec4ba55c960e989a589188a37251b591e5bf4cb2ed09b7d24563f056ac`.
- Feedback `edb1fe7584308785f5aed11086f2a51184e7318041bff5d459751541514cd39e`;
  lineage `a784343b2d3cc8efb6bb2a3c8f1011de0a511e61cf68f82769de6abfb53cccd4`;
  result `603ee0104b3c1092ebc098bc394ee0fe0ad7fd52f295f56aced6d04e32738ae6`.
- Target fixture integrity: `git diff --exit-code -- examples/python/simple-layered-app` passed.
- Secret scan: no key-shaped value found. Orphans: one expected primary worktree, no containers.
- GitHub Actions: not executed locally; workflow configuration passed YAML/pre-commit checks.
