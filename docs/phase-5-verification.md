# Phase 5 verification

## Provenance and hardening audit

Phase 5 was introduced by `cf2358d` (`feat: add isolated patch architecture validation`) and
merged into local `main` by `e1c540b6c47c2b211909274afc87e4cca5a43ada`. The Phase 4 commit
`009f489c55142185dccf50016bc05ef3f6701b05` is an ancestor. The audit used that local main
merge as its authoritative baseline; no remote or GitHub operation was performed. Package and
citation metadata remain at version 0.5.0.

The initial implementation was functional but required hardening. Static diff inspection treated
metadata-like hunk content as metadata, did not reject every gitlink mode form, and did not bind
decoded patch metadata to its own fingerprint. Repository-state proof covered untracked names but
not their file contents. Worktree cleanup suppressed failures and lacked post-cleanup verification.
Result persistence lived in the CLI rather than the application service, and application failures
could return before cleanup. Several decoded domain invariants and adversarial executable tests were
also absent. The shipped introduced/resolved examples did not apply to the current example tree.

The hardening corrects those issues while retaining textual regular-file add/modify/delete support.
Patch text remains untrusted: it is size-bounded, parsed without shell evaluation, rejected for
unsafe paths/formats/modes, and applied only by argument-array Git commands in a detached temporary
worktree with hooks disabled and submodules left uninitialized. Patched Python is parsed as data and
is never imported, tested, or executed.

## Actual local verification

Environment: macOS arm64, uv 0.11.32, Python 3.12.13 and 3.13.13, Docker Desktop.

| Check | Actual result |
| --- | --- |
| `uv lock --check`; `uv sync --frozen` | passed; 48 resolved, 47 checked |
| `ruff format --check .`; `ruff check .` | passed; 134 files, no findings |
| `mypy src tests` | passed; 80 source files |
| full suite, Python 3.12 | 405 passed, 2 upstream deprecation warnings |
| full suite, Python 3.13 isolated | 405 passed, 2 upstream deprecation warnings |
| coverage, Python 3.12 | 98.40% statements (2,893/2,940); 94.70% branches (572/604); 97.77% combined |
| Phase 5 domain/inspector unit subset | 36 passed |
| Phase 5 real-Git/CLI integration subset | 14 passed |
| architecture tests | 22 passed |
| `uv build` | built 0.5.0 sdist and wheel |
| `archguard version`; `archguard doctor` | 0.5.0; all required checks passed |
| all Phase 5 result commands and four state filters | passed |
| safe patch, twice | exit 0; byte-identical artifacts |
| introduced violation | exit 1; one introduced violation |
| resolved violation | exit 0; one resolved violation |
| traversal, Git metadata, binary, malformed patches | exit 3 without traceback or patch-content output |
| non-applicable patch | exit 5 with canonical failure artifact |
| CFF 1.2 validation; `docker compose config` | passed |
| `make architecture-self` | passed; 88 modules, 7 rules, zero violations |
| `docker build -t archguard-apr:phase-5 .` | passed; image `2b47129437a4…e9a60f5d` |

The final Phase 5 surface has 29 focused test functions: 15 unit, 5 CLI integration, and 9
worktree integration functions. Parameter expansion yields 36 unit cases and 14 real-Git/CLI
cases. Adversarial cases cover malformed/truncated headers, absolute POSIX and Windows paths,
traversal, backslashes, Unicode, control/NUL bytes, case-insensitive `.git`, protected/out-of-root
paths, duplicate and excessive operations, overlong paths, oversized input/artifacts/Git output,
binary/rename/copy/mode/gitlink metadata, symlink artifacts, tampered fingerprints, duplicate JSON
keys, non-finite JSON numbers, unknown fields, timeouts, partial creation, and cleanup exceptions.

## Determinism and isolation evidence

For two validations against the same temporary committed repository, the canonical result bytes
were identical. Both files had SHA-256
`c0bc6eda84434e625f70a4383a80ce499bc7040ff77f33d736cc6dc274f2dddd`.
Embedded identities were patch metadata
`ddd2815264f7c9c57fb437f6aa16c4fa10c5df703bf962468e099fd87e7ad11d`, patch bytes
`6de9856c746338d21b0bf4c5b06f3d9b2dbc07d318650e6fdd5c34a0e65a0624`, delta
`6c36e3e7cf112388b673a82b7216e53c56615e49797bbbe6e5bd916b35394def`, and result
`733ba8dc0fb14e0051d6c33239296638ae82b3f8df2e1ba7afaff5e7edf91216`.

Before/after capture proved identical original HEAD, branch, index tree, tracked status, untracked
name hash, and untracked type/content hash. Real-Git tests prove success, rejection, applicability
failure, timeout after registration, partial creation failure, and exception paths. Cleanup is
idempotent, validates owned temporary paths, removes registrations and directories, and verifies
both are absent. The final smoke repository reported zero `archguard-candidate-*` registrations.

## Limitations

Architecture conformance does not prove runtime correctness. Dynamic imports and unsupported or
generated source types retain the Phase 2 analyzer limitations. Patch support intentionally excludes
renames, copies, symlinks, gitlinks/submodules, binary patches, and dirty baselines. Output paths are
immutable rather than overwritten. The two warnings are upstream Starlette/httpx and AnyIO
deprecations. No release, tag, remote synchronization, GitHub action, experiment execution, patched
application execution, or repair generation occurred during this local audit.
