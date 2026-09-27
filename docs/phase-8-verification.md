# Phase 8 verification

Baseline was clean merged `main` at `d48031b7c66325d7009664f7bcf6b95bd133a617`, version 0.7.0.
The baseline suite produced 464 passed and 3 explicitly Docker-gated skips at 94.02% combined
coverage. Phase 5 isolated validation, Phase 6 context retrieval, and Phase 7 sandbox feedback were
present. No network Git operation was performed.

The controlled provider-free demonstration completed with 15 chained events, one architecture-
rejected candidate, one validated/selected candidate, explicit human approval, verified checkpoint
resume, and replay with zero agent invocations and zero executions. Two independent runs were
byte-identical:

| Artifact | SHA-256 |
| --- | --- |
| specification | `d50ae5cc34362bf1d4aa6cce54bdbb8adc2e9a48eae0d967cffc8321b56267f7` |
| event log | `a41e65488982a1abc2bebf62bc053eb9cf9c00efa02bea137049950ea351a179` |
| checkpoint | `d00ecb81d58626ea2b4b1287abfb4921846b4d4ccbcb3c3ed857928b0d405f64` |

## Final local verification

| Check | Observed result |
| --- | --- |
| Python 3.12 | 486 passed, 3 Docker-gated skips |
| Python 3.13 non-Docker | 486 passed, 3 deselected |
| Phase 8 focused | 22 passed |
| Phase 5/6/7 regression subset | 66 passed |
| Phase 7 Docker isolation | 3 passed |
| Ruff / strict mypy / pre-commit | passed; 106 typed source files; all hooks passed |
| Statement coverage | 4705/4977, 94.53% |
| Branch coverage | 911/1034, 88.10% |
| Combined coverage | 93.43% |
| Package | 0.8.0 sdist and wheel built |
| Docker | Compose valid; `archguard-apr:phase-8` image `e43513b9…1bc0` built |
| Self architecture | 121 modules, 7 rules, zero violations, passed |
| Cleanup | zero Phase 7/8 containers; only the primary worktree |

All canonical artifacts were written outside the repository. The primary HEAD remained at the
recorded baseline throughout demonstrations and validation; scripted agents performed no I/O.
This is mechanism-level engineering evidence, not an empirical repair result.

Limitations: agents are scripted; no provider or API is connected; confidence is not evidence;
future providers may be nondeterministic; hash chaining is not authorship; Docker remains trusted;
passing selected tests is not proof of correctness. GitHub Actions is configured but was not run
locally.
