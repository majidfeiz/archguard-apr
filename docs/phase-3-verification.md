# Phase 3 verification

## Baseline and scope

Started with a clean Phase 2 worktree. Fetched public main over HTTPS after SSH authentication
failed, verified accepted commit `e2ff3484e629a0b476c2e6b3f50891b5be971c39`, fast-forwarded local
main, then created `phase/03-repository-graph`. The accepted Phase 2 implementation
`306f41c095fbf90cc54e7aeb11adb02afef4a639` is recorded in the task; authoritative baseline is the
main SHA above. Baseline tests: **199 passed, 98.41% coverage**, Python 3.12.13.

Version is **0.3.0**. This change adds immutable graph schema v1, conservative import resolution,
canonical graph persistence and deterministic structural queries. No architecture inference,
constraint validation, call graph, execution, LLM, agent, MCP or HTTP graph API was added.

## Local verification

| Check | Result |
| --- | --- |
| `uv lock --check`, `uv sync --frozen` | Passed; no runtime dependencies added |
| `uv run ruff format --check .`, `uv run ruff check .` | Passed |
| `uv run mypy src tests` | Passed, strict, 60 source files |
| `uv run pytest`, Python 3.12.13 | 226 passed; 98.78% combined statement/branch coverage |
| Isolated `uv run --python 3.13 pytest`, Python 3.13.13 | 226 passed; 98.78% coverage |
| `PYTEST_ADDOPTS=--no-cov uv run pytest -m architecture` | 22 passed |
| `uv run archguard version` | `0.3.0` |
| `uv run archguard doctor` | All required checks true; daemon intentionally not probed |
| Example analyze/build/inspect/query workflow | Passed |
| Repeated graph `cmp` and SHA-256 | Byte-identical |
| `uv run python scripts/benchmark_repository_graph.py` | See engineering measurement below |
| `uv build` | Wheel and source distribution built |
| `uv run pre-commit run --all-files` | Passed |
| `docker compose config`, `docker build -t archguard-apr:phase-3 .` | Passed |
| `git diff --check` | Passed |

The architecture subset disables coverage because it cannot measure whole-program behavioral
coverage; the full suite retains the mandatory 90% gate. Both Python suites emit two existing
upstream Starlette/HTTPX/AnyIO deprecation warnings. Third-party Action versions were unchanged.
CI retains both Python versions, strict typing, lint, tests, package/Docker builds and adds graph
build/inspect/cycles smoke commands. No artifact or image publishing step was added.

## Determinism and example queries

The unmodified `examples/python/simple-layered-app` analyzed with `--source-root src` yields five
files/modules. Graph: **16 nodes, 18 edges**, 4 import occurrences (3 internal, 1 external), no
diagnostics, complete status. Files `/tmp/archguard-graph-1.json` and
`/tmp/archguard-graph-2.json` are byte-identical.

```text
snapshot artifact SHA-256:
78c712e943e4f72b967c9d320f5c40361a1e9881c0e0c5af2f32cd1f6f034c97
snapshot fingerprint:
ad09abd701d30e176e1d25cebee10708e622d4e813e1e6e05809a0a00741beb4
graph artifact SHA-256 (both files):
868c0a1fff10a7005d449a301f4f21c8ca924b0a9112e9af49d256c022b3e4fa
graph fingerprint:
c7f20d25217fb02ba12295d943de8d9e778f7a2ed4786205a60f7f6901250274
```

```bash
uv run archguard graph dependencies /tmp/archguard-graph-1.json module:demo.service
# ["module:demo.repository"]
uv run archguard graph path /tmp/archguard-graph-1.json module:demo.controller module:demo.model
# ["module:demo.controller", "module:demo.service", "module:demo.repository", "module:demo.model"]
uv run archguard graph cycles /tmp/archguard-graph-1.json
# []
```

Tests verify location-independent bytes, stable query output, lexical shortest-path tie-breaking,
iterative SCCs on a 3,001-node chain, self-import and TYPE_CHECKING-only cycles. They preserve
nested/repeated symbols, skipped/failed files, distinct and exact-duplicate import occurrences,
ambiguous owners, unresolved relative imports and source-free diagnostics. Corrupt schemas,
unknown fields, duplicate keys, nonfinite numbers, invalid identities/references, summary and hash
mismatches fail. Size limits, symlinks, protected roots, input replacement and atomic-write cleanup
are exercised. Mocked source reads/subprocess calls fail if graph construction attempts them.
Examples have no Git diff; graph data contains only validated relative paths and syntax metadata,
not source contents, timestamps or checkout location. Snapshot artifacts remain byte-compatible
with Phase 2 after sharing canonical JSON and atomic I/O utilities.

Docker smoke: non-root image with read-only filesystem, no network and a read-only snapshot mount
passed build/inspect/cycles. Linux Python 3.12.14 produced the same graph SHA-256 as macOS above.
Local image ID: `sha256:0cad5c63014895b6401d0206a4047e8b13eaa305dd6d3e261d6d8cfce33d6c17`.

## Engineering measurement

One local run: 500 files, 500 modules, 2,000 function symbols, 1,000 imports → **3,001 nodes,
4,000 edges, 2,116,364 canonical bytes**, construction including domain validation **0.132620 s**.
Fixture creation/AST parsing and artifact serialization are outside the timed interval. This is
an environment-specific engineering measurement, not a timing guarantee or scientific experiment.

## Files and review

New domain graph/canonical/resolution/validation modules; application graph ports and build/inspect/
query services; infrastructure graph artifacts and shared byte/JSON utilities; graph CLI; graph unit
fixtures/tests; benchmark script; graph architecture, schema and ADR-0004 documentation.
Updated version/lock/citation/changelog, CLI composition, snapshot persistence utilities, affected
existing tests, README, contributor guidance, development/research/integration docs, Makefile and CI.

Known limitations and exact identity framing are in [graph architecture](architecture/repository-graph.md)
and [schema](schemas/repository-graph-v1.md). External syntax does not identify distributions; dynamic
imports and runtime attributes are not resolved. Callers supply protected-root context explicitly.
Hashes provide integrity/reproducibility, not authenticity. Review the Phase 3 PR before merge;
no tag, release or merge is part of this task.
