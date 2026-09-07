# Phase 5 verification

Baseline: `54b00e5653171011c6c68cd53debf2a05282864c`, package 0.4.0, 354 tests passed,
99.16% combined statement/branch coverage. Implementation version: 0.5.0.

Phase 5 adds immutable candidate patch, state proof, semantic delta, and validation result values;
narrow ports and orchestration; bounded unified-diff inspection; detached Git worktrees; canonical
artifact I/O; CLI commands; real-Git/adversarial tests; schemas, ADRs, security and research updates.

Supported: textual regular-file add/modify/delete. Rejected: empty, oversized, NUL, malformed,
absolute/traversal/`.git`/control/overlong/protected/out-of-root paths, duplicate operations, binary,
rename/copy, symlink, and gitlink patches. Applicability failure is distinct from static rejection.

Threat-model tests cover path policy, unsafe modes and formats, exact-byte identity, clean baseline,
isolated application, original state equality, exception cleanup, and orphan registration removal.
No patched code, hook, submodule, test, network operation, or arbitrary candidate command executes.

Verification on macOS arm64, Python 3.12.13, Git 2.x, uv 0.11.32, and Docker Desktop:

| Command | Actual result |
| --- | --- |
| `uv lock --check` / `uv sync --frozen` | passed; 48 resolved / 47 checked packages |
| `ruff format --check` / `ruff check` | passed; 133 files formatted, no lint findings |
| `mypy src tests` | passed; 80 source files |
| `pytest` | 374 passed; 96.51% combined statement/branch coverage |
| architecture subset (`--no-cov`) | 22 passed |
| `uv build` | built 0.5.0 sdist and wheel (ignored build output) |
| `archguard version` / `doctor` | 0.5.0; all required checks passed |
| Phase 2–4 CLI smokes | analyze/inspect/build/query/profile/evaluate all passed |
| Phase 5 CLI/determinism smokes | 5 passed; two validation artifacts byte-identical |
| `pre-commit run --all-files` | all eight hooks passed |
| `cffconvert --validate` | passed; YAML/version fallback also passed |
| `docker compose config` | passed |
| `docker build -t archguard-apr:phase-5 .` | passed; image `bbcf0516…a06` |
| `git diff --check` | passed |

The fixed local smoke validation artifact was 3,318 bytes with SHA-256
`4b497111ceceae18a80afd7c6444d858ed07cd52c8adc176850faaf9efe3a497`; its embedded
result fingerprint was `5b4c398fa79f945bfe9f51eb4d95df16ee1259ffd52bdf48f53534add1b71bab`.
The deterministic Phase 5 real-Git guardrail (two complete validations plus cleanup/failure cases)
took 1.06 seconds wall clock locally; this is an engineering observation, not a benchmark claim or
CI threshold. No candidate worktree registrations or adapter temporary directories remained.

The only test warnings were upstream Starlette/httpx and AnyIO deprecations. An initial sandboxed
Docker attempt could not resolve registries; the approved network-enabled retry passed. Static
architecture conformance and resolved violations do not imply functional correctness. Dynamic
imports and unsupported/generated source types remain analyzer limitations. No release, tag, merge,
candidate execution, experimental result, or repair-generation behavior was created.
