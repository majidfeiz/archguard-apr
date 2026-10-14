# Public-release file inventory

The baseline contains 601 tracked files and no untracked files. The largest tracked files are the four publication documents (approximately 24–348 KiB); no tracked file approaches GitHub's large-file limit.

| Class | Paths | Release assessment |
|---|---|---|
| software | `src/`, `scripts/`, `configs/`, `examples/` | public under Apache-2.0, subject to per-file notices |
| tests | `tests/` | public; credential/path examples are synthetic fixtures |
| workflows/templates | `.github/` | public; review permissions and action pinning before publication |
| documentation | `docs/`, root Markdown | public under documented scope |
| research records | `research/` | public only where canonical and source-free |
| manuscripts/data | `paper/` | author-owned material public under `paper/LICENSE.md`; bibliography and third-party material retain original terms |
| binary publications | `paper/dist/*.docx`, `paper/dist/*.pdf` | generated but intentionally tracked; hashes verified |
| external benchmarks | metadata and fingerprints only | no repository, dataset payload, gold patch, or evaluator-only asset redistributed |
| ignored local state | `.env*`, `.venv/`, caches, coverage, `dist/`, `htmlcov/` | excluded from Git |
| restricted | provider payloads, credentials, benchmark source, gold patches, raw logs, temporary worktrees, external ZIP files | must remain outside Git |

Generated paper charts are safe source-free aggregates. Local `.DS_Store`, coverage, caches, and Python bytecode are ignored and were not added. See the [artifact policy](public-artifact-policy.md) for the controlling classification.
