# Phase 2 verification record

## Baseline and scope

Started from clean `main` and local `origin/main` at
`876d03b4d78da0565236fcbc21b197de017a061f`. The baseline suite passed: 108 tests,
98.17% combined coverage. The supplied acceptance record identified GitHub run 33953156741
with both Python jobs and Docker passing; that remote run was user-provided, not reverified here.
`git fetch origin main` failed with SSH `Permission denied (publickey)`. The accepted local
baseline was verified directly. GitHub CLI also has no authenticated account in this environment.
No user changes existed or were replaced. Work is on `phase/02-repository-analysis`, never main.

Implemented version 0.2.0: deterministic read-only Python discovery/AST extraction, immutable
canonical snapshots, separate analysis/persistence ports and application use cases, analyze/inspect
CLI, typed policy configuration, examples and tests. No additional runtime dependency was added;
uv.lock changed only the project version. No graph, architecture inference, repair, LLM or agent
capability was added. HTTP retains health/readiness/version endpoints only.

## Actual verification outcomes

| Command | Result |
| --- | --- |
| `git status` | Clean accepted baseline initially; only Phase 2 changes before commit |
| `uv lock --check` | Passed |
| `uv sync --frozen` | Passed; project updated to 0.2.0 |
| `uv run ruff format --check .` | Passed |
| `uv run ruff check .` | Passed |
| `uv run mypy src tests` | Passed; 47 source/test files |
| `uv run pytest` | 199 passed on Python 3.12.13; 98.41% combined statement/branch coverage |
| Python 3.13 isolated-environment complete suite | 199 passed on Python 3.13.13; 98.41% coverage |
| `uv run pytest -m architecture` with `PYTEST_ADDOPTS=--no-cov` | 22 passed; 177 deselected |
| `uv run archguard version` | 0.2.0 |
| `uv run archguard doctor` | Passed; Python/config/paths/Git/Docker executable available |
| `uv run archguard repository analyze examples/python/simple-layered-app --source-root src --output /tmp/archguard-analysis.json` | Passed; 5 parsed files, 0 failures/diagnostics |
| `uv run archguard repository inspect /tmp/archguard-analysis.json` | Passed |
| Repeat analysis to `/tmp/archguard-analysis-repeat.json` | Passed; byte-identical output |
| `uv build` | Built 0.2.0 wheel and source distribution |
| `uv run pre-commit run --all-files` | All eight hooks passed |
| `docker compose config` | Passed |
| `docker build -t archguard-apr:phase-2 .` | Passed |
| Read-only, network-disabled Linux container smoke | Non-root UID 10001; version 0.2.0; canonical hash matches macOS |
| `git diff --check` and staged whitespace check | Passed |
| `uv run python scripts/benchmark_repository_analysis.py` equivalent interpreter invocation | 500 files parsed; one local run took approximately 0.042 seconds |

The performance invocation is an engineering guardrail, not a scientific result. Two upstream
Starlette/HTTPX/AnyIO deprecation warnings remain. The full-suite coverage threshold increased
from 85% to 90%; focused architecture-only execution explicitly disables coverage because static
checks alone do not measure whole-program behavior. No test hook or threshold bypass was added.

Final Docker image ID: `sha256:55c2345825bac066e221fc75017e974a3c8f77e74e72527179f097d0a2643966`.
Python base manifest digest: `sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea`.
The Linux runtime reported Python 3.12.14 during build.

## Determinism and read-only evidence

Both `archguard-analysis.json` and `archguard-analysis-repeat.json` have SHA-256:

`78c712e943e4f72b967c9d320f5c40361a1e9881c0e0c5af2f32cd1f6f034c97`

Repository fingerprint:

`ad09abd701d30e176e1d25cebee10708e622d4e813e1e6e05809a0a00741beb4`

Byte comparison passed. The same artifact hash was independently reproduced inside Linux Docker
with the example mounted read-only. The complete example JSON was inspected: schema 1, sorted
paths, 5 modules, 1 class, 3 sync functions, 4 import statements, 452 raw bytes, 22 physical lines,
0 failures/diagnostics; all per-file hashes/counts matched the actual example files. No host path,
source text, environment, credentials or timestamps were present.

A manifest including paths, file types, file hashes and symlink targets was compared before and
after both actual CLI analyses: exact equality. Automated tests also cover fixture manifest equality,
outside symlinks, symlink substitution before open, top-level side-effect prevention, forbidden
subprocess/evaluation, write-failure cleanup, configuration/content changes and discovery-order
invariance. The example's unchanged manifest is recorded below:

```json
{
  "README.md": [
    "file",
    "7b283d8b892d54b8ec254014479879a9fdfabcc9bdda86dbeabb84e75d4cb2fc"
  ],
  "src": [
    "directory",
    ""
  ],
  "src/demo": [
    "directory",
    ""
  ],
  "src/demo/__init__.py": [
    "file",
    "22a2a70655aec003a6210745b40cbfbd17624fa8f0aab63a859c7ffc14e4ad85"
  ],
  "src/demo/controller.py": [
    "file",
    "c282ee8b62062554ab6bbebf78cf31bd98ebf5531dd8d31383386a50b2ca5ea8"
  ],
  "src/demo/model.py": [
    "file",
    "fd5ad3decf9c01d4cc1a5be2d32993e2233bdc39b2fc85ad02e9f034b9ab69bd"
  ],
  "src/demo/repository.py": [
    "file",
    "f3e807d5aea170e4512c31fc7ef7a178c56bf2331f17a692b2db0c369c6aa0af"
  ],
  "src/demo/service.py": [
    "file",
    "e789f8738639e2a09a0843582bb0141d1683a14b1f8cca957ba1bc26203ea727"
  ]
}
```

## Decisions and limitations

RepositoryAnalyzerPort now returns RepositorySnapshot and accepts AnalysisOptions; writer/reader
ports isolate storage. ArtifactReference gains an optional SHA-256. Symbol IDs use relative file,
qualified name and source position to retain duplicate definitions. Fingerprints hash a framed
canonical JSON object containing schema, fixed parser grammar, sorted options and sorted readable
file path/content-digest pairs. Full artifact hashes are separate.

Default traversal excludes generated directories, omits hidden paths and never follows symlinks.
Outputs must be outside target roots. Source records may be failed/skipped with null digests where
complete contents cannot safely be read; partial fingerprints do not identify unread bytes. Unix
safe-descriptor APIs are required; Windows analysis fails closed. Concurrent hostile filesystem
mutation, mount/hard-link provenance, global parser resource isolation, semantic imports and
architecture inference remain out of scope. `.gitignore` is not interpreted. Names/paths can be
sensitive metadata even though source and host identity are omitted. See the schema and ADR-0003.

Next: push this branch from an authenticated Git environment, run GitHub's Python 3.12/3.13 and
Docker jobs, then review the change against main without automatic merging. Commit/push results
are reported in the delivery message; no release or tag is created.

## Created and modified files

- Modified: `.env.example`
- Modified: `.github/workflows/ci.yml`
- Modified: `AGENTS.md`
- Modified: `CHANGELOG.md`
- Modified: `CITATION.cff`
- Modified: `Makefile`
- Modified: `README.md`
- Modified: `configs/app.example.yaml`
- Created: `docs/architecture/decisions/ADR-0003-canonical-repository-snapshot.md`
- Modified: `docs/architecture/decisions/README.md`
- Modified: `docs/architecture/overview.md`
- Created: `docs/architecture/repository-analysis.md`
- Modified: `docs/development.md`
- Created: `docs/phase-2-verification.md`
- Modified: `docs/research/research-protocol.md`
- Created: `docs/schemas/repository-snapshot-v1.md`
- Created: `examples/python/simple-layered-app/README.md`
- Created: `examples/python/simple-layered-app/src/demo/__init__.py`
- Created: `examples/python/simple-layered-app/src/demo/controller.py`
- Created: `examples/python/simple-layered-app/src/demo/model.py`
- Created: `examples/python/simple-layered-app/src/demo/repository.py`
- Created: `examples/python/simple-layered-app/src/demo/service.py`
- Modified: `pyproject.toml`
- Created: `scripts/benchmark_repository_analysis.py`
- Modified: `src/archguard/__init__.py`
- Modified: `src/archguard/application/ports/repository.py`
- Created: `src/archguard/application/services/repository.py`
- Modified: `src/archguard/domain/models.py`
- Created: `src/archguard/domain/repository.py`
- Modified: `src/archguard/entrypoints/cli/app.py`
- Created: `src/archguard/entrypoints/cli/repository.py`
- Modified: `src/archguard/infrastructure/config.py`
- Created: `src/archguard/infrastructure/python_parser.py`
- Created: `src/archguard/infrastructure/repository_analyzer.py`
- Created: `src/archguard/infrastructure/repository_artifacts.py`
- Created: `src/archguard/infrastructure/repository_codec.py`
- Created: `tests/__init__.py`
- Modified: `tests/architecture/test_dependency_rules.py`
- Created: `tests/fixtures/repositories/malicious.py.txt`
- Created: `tests/fixtures/repositories/structure.py.txt`
- Modified: `tests/integration/test_api.py`
- Modified: `tests/integration/test_cli.py`
- Modified: `tests/integration/test_imports.py`
- Created: `tests/integration/test_repository_cli.py`
- Created: `tests/unit/__init__.py`
- Modified: `tests/unit/test_ports.py`
- Created: `tests/unit/test_repository_analysis.py`
- Created: `tests/unit/test_repository_artifacts.py`
- Modified: `uv.lock`
