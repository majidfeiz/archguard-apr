# Phase 1 verification record

Local verification used Python 3.12.13 and uv 0.11.32 on macOS.
The repository initially contained only Git metadata, had no commits, and was on `main`.
No user files were replaced. All paths listed below are new.

| Command | Actual result |
| --- | --- |
| `uv sync --frozen` | Passed; 47 installed packages checked |
| `uv lock --check` | Passed |
| `uv run ruff format --check .` | Passed |
| `uv run ruff check .` | Passed |
| `uv run mypy src tests` | Passed; 35 source/test files |
| `uv run pytest` | 108 passed; 98.17% combined statement/branch coverage |
| `uv build` | Built wheel and source distribution for 0.1.0 |
| `uv run archguard version` | Passed; 0.1.0 |
| `uv run archguard doctor` | Passed; Python/config/paths/Git available; Docker executable available, daemon explicitly not checked |
| `uv run archguard config show` | Passed; provider execution disabled |
| `uv run archguard experiment validate --config configs/experiments/smoke.yaml` | Passed; metadata only |
| `docker compose config` | Passed |
| `docker build -t archguard-apr:phase-1 .` | Failed before build: Docker daemon socket missing |
| `uv run pre-commit run --all-files` | All eight hooks passed |
| `uvx --from cffconvert cffconvert --validate` | CFF 1.2.0 schema valid |
| `git diff --cached --check` | Passed |
| `git ls-remote origin HEAD` | SSH authentication failed: Permission denied (publickey); push not attempted |

Two upstream deprecation warnings originate in Starlette's HTTPX test client and its AnyIO
BlockingPortal alias. They do not fail tests. Python 3.13 is configured in CI but was not
executed locally. GitHub CI has not run because this checkout has not been pushed.
Container build/runtime behavior is unverified until Docker is running.

The reviewed implementation preserves the requested structure. Additions are `.python-version`
for interpreter selection, `docs/LICENSE.md` for documentation licensing, this record, and
focused logging, port-contract and import-side-effect tests. No Phase 2 engine is implemented.
The service package contains no speculative classes. Ports return artifact references rather
than premature graph/patch objects. Provider execution is explicitly rejected in Phase 1.

Next: start Docker and rerun the documented image build. Configure GitHub SSH authentication
before `git push -u origin main`. Then verify CI before starting the literature/dataset decisions
for a later phase. The final commit hash and working-tree state are reported in the delivery message.

## Created-file inventory

- `.dockerignore`
- `.editorconfig`
- `.env.example`
- `.github/ISSUE_TEMPLATE/bug_report.yml`
- `.github/ISSUE_TEMPLATE/research_task.yml`
- `.github/pull_request_template.md`
- `.github/workflows/ci.yml`
- `.gitignore`
- `.pre-commit-config.yaml`
- `.python-version`
- `AGENTS.md`
- `CHANGELOG.md`
- `CITATION.cff`
- `CODE_OF_CONDUCT.md`
- `CONTRIBUTING.md`
- `Dockerfile`
- `LICENSE`
- `Makefile`
- `README.md`
- `SECURITY.md`
- `configs/app.example.yaml`
- `configs/experiments/smoke.yaml`
- `docker-compose.yml`
- `docs/LICENSE.md`
- `docs/architecture/decisions/ADR-0001-agent-agnostic-core.md`
- `docs/architecture/decisions/ADR-0002-python-tooling.md`
- `docs/architecture/decisions/README.md`
- `docs/architecture/integration-strategy.md`
- `docs/architecture/overview.md`
- `docs/development.md`
- `docs/integrations/claude-code.md`
- `docs/integrations/codex.md`
- `docs/integrations/mcp.md`
- `docs/phase-1-verification.md`
- `docs/research/experiment-registry.md`
- `docs/research/literature-matrix-template.csv`
- `docs/research/research-protocol.md`
- `docs/research/research-questions.md`
- `experiments/README.md`
- `experiments/manifests/README.md`
- `experiments/results/README.md`
- `pyproject.toml`
- `src/archguard/__init__.py`
- `src/archguard/__main__.py`
- `src/archguard/application/__init__.py`
- `src/archguard/application/ports/__init__.py`
- `src/archguard/application/ports/architecture.py`
- `src/archguard/application/ports/execution.py`
- `src/archguard/application/ports/repair.py`
- `src/archguard/application/ports/repository.py`
- `src/archguard/application/services/__init__.py`
- `src/archguard/domain/__init__.py`
- `src/archguard/domain/enums.py`
- `src/archguard/domain/errors.py`
- `src/archguard/domain/models.py`
- `src/archguard/entrypoints/__init__.py`
- `src/archguard/entrypoints/api/__init__.py`
- `src/archguard/entrypoints/api/app.py`
- `src/archguard/entrypoints/cli/__init__.py`
- `src/archguard/entrypoints/cli/app.py`
- `src/archguard/infrastructure/__init__.py`
- `src/archguard/infrastructure/config.py`
- `src/archguard/infrastructure/logging.py`
- `src/archguard/infrastructure/paths.py`
- `src/archguard/schemas/__init__.py`
- `src/archguard/schemas/api.py`
- `src/archguard/schemas/experiment.py`
- `tests/architecture/test_dependency_rules.py`
- `tests/conftest.py`
- `tests/integration/test_api.py`
- `tests/integration/test_cli.py`
- `tests/integration/test_imports.py`
- `tests/unit/test_config.py`
- `tests/unit/test_domain_models.py`
- `tests/unit/test_experiment_schema.py`
- `tests/unit/test_logging.py`
- `tests/unit/test_ports.py`
- `uv.lock`
