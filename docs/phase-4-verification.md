# Phase 4 verification

## Baseline and scope

Verified on 2026-09-06 in the supplied macOS arm64 checkout, using uv 0.11.32.
The initial working tree was clean on Phase 3 commit
`8a98112e15d34b04d999484a02abd493a188bc2c`. Local main was behind the accepted baseline;
SSH fetch failed authentication. HTTPS fetch succeeded, main fast-forwarded to
`ca491325eb6aefe21bc50b469aba47f917175d5d`, and ancestry was verified before creating
`phase/04-constraint-engine`. No implementation edit was made on main.

Actual baseline: package 0.3.0; Python 3.12.13; 226 tests passed; 98.78% combined statement/branch
coverage. No user changes were present. The Phase 4 request explicitly superseded the previous
Phase 3 constraint-engine prohibition in AGENTS.md, which is now updated.

Implementation: package 0.4.0; independent profile/report schemas v1; six replacement architecture
ports; four explicit rule types; source-free aggregate evidence; strict canonical artifacts;
CLI, examples, self-hosting CI, shared SCC utility, engineering workload and documentation.
No inference, patch comparison, LLM, agent, repair or product integration was added.

## Local verification results

| Check | Actual result |
| --- | --- |
| `git status` before work | Clean; Phase 3 branch |
| `uv lock --check` | Passed; 48 packages resolved |
| `uv sync --frozen` | Passed; editable package updated to 0.4.0 |
| `uv run ruff format --check .` | Passed |
| `uv run ruff check .` | Passed |
| `uv run mypy src tests` | Passed; 70 source files |
| `uv run pytest`, Python 3.12.13 | 354 passed; 99.16% combined coverage |
| Python 3.13.13 complete suite | 354 passed; 99.16% combined coverage |
| Architecture subset | 22 passed, 332 deselected |
| `uv run archguard version` | 0.4.0 |
| `uv run archguard doctor` | Passed all required prerequisites |
| Example analysis / graph build | Complete, five modules; exit 0 |
| Graph inspect / cycle query | Passed; no cycles |
| Profile validate / compile twice / inspect | Passed |
| Profile `cmp` and SHA-256 | Byte-identical |
| Passing evaluation twice | Passed, complete; four evaluated rules; no violations |
| Report `cmp` and SHA-256 | Byte-identical |
| Report inspect / violations | Passed; empty violation list for compliant profile |
| Violating profile evaluation | Expected exit 1; one error dependency violation; complete |
| Self-hosting | Exit 0; 78/78 assigned; seven evaluated rules; no violations; complete |
| Constraint engineering workload | Completed; measurements below |
| `uv build` | Passed; 0.4.0 sdist and wheel built, not committed |
| `docker compose config` | Passed |
| `docker build -t archguard-apr:phase-4 .` | Passed; image details below |
| `git diff --check` | Passed |

The architecture-only invocation uses the established repository convention
`PYTEST_ADDOPTS=--no-cov uv run pytest -m architecture`; it does not replace or weaken the full-suite
coverage gate. Python 3.13 used `UV_PROJECT_ENVIRONMENT=/tmp/archguard-phase4-py313` and a separate
coverage file. Existing two Starlette/AnyIO deprecation warnings remain. No Action versions were
changed to suppress Node.js warnings. Initial sandbox attempts to access uv cache/network and Docker
socket failed; approved execution with required access succeeded. No test failures remain.

`uv run pre-commit run --all-files` passed all eight hooks on the staged Phase 4 tree.
`git diff --cached --check` passed. The reviewed change contains 43 files; generated artifacts,
coverage files, build outputs and verification logs are excluded from the commit. Publication
metadata is recorded in the pull request and final handoff; no merge, release or Git tag is authorized.

## Deterministic artifact identities

All following hashes were computed from actual local artifacts. Both profile destinations contain
identical bytes; both report destinations contain identical bytes. No generated JSON is committed.

| Identity | SHA-256 |
| --- | --- |
| Example graph fingerprint | `c7f20d25217fb02ba12295d943de8d9e778f7a2ed4786205a60f7f6901250274` |
| Compliant profile fingerprint | `b3a204134aa81053e78c063ebadaa564e963157957ac35b6bce19e0b4747ff32` |
| Profile artifact 1 and 2 | `49fe7b8ac30e7cff461dbd08e6b90b3d0cdfd57ee4f63610ca6d869b0a7f361f` |
| Compliant report fingerprint | `5cd7f43f489f7a7248e681f0c3fb8b7ad5e85d8bd05e2cf2afda4fc1c1a108c7` |
| Report artifact 1 and 2 | `39def01cd60ce8a73de2404034fc6b73b7ac0b1bf8c1a9aa91a04a3a8b6c05a9` |
| Violating profile fingerprint | `a8ddb61bacb216b72c18b513eca2f510bc647a40b77299903e977b980b0f1990` |
| Violating report fingerprint | `3dca93a3cf9f996680a083c0776e0792f612e362a2df4c51899cd1107f6321c1` |
| Violating report artifact | `52e51aa77d4ce4c201994f4f64f1e1313cab4fa6d72ec66003bd791d03154e75` |
| Self-hosting profile fingerprint | `d00fbb7aebd3a23f5d1f3e004abd15dc8c86615d872e2b4516686f5dca85cf26` |
| Self-hosting graph fingerprint | `a8c5fa43e783daaa0087c2a5150de24991aa613a38b430036e0f88262903ddc5` |
| Self-hosting report fingerprint | `7482a27e09ba736ff2f824408a196e30898e3d027e0eedc4922ed334f85b24ee` |
| Self-hosting report artifact | `eaef4875ab787625308b9ac826d4ea18733174238ff57b8eec011e007b5bfc9b` |

Self-hosting hashes describe the verified source/test tree; documentation-only changes do not enter
the snapshot's Python source identity. Report/profile fingerprints hash canonical semantic objects;
artifact hashes hash full persisted bytes. Exact framing is in both schema documents.

## Reproduce the complete workflow

```bash
uv run archguard repository analyze examples/python/simple-layered-app \
  --source-root src --output /tmp/archguard-snapshot.json
uv run archguard graph build /tmp/archguard-snapshot.json --output /tmp/archguard-graph.json
uv run archguard architecture profile validate examples/architecture/simple-layered.yaml
uv run archguard architecture profile compile examples/architecture/simple-layered.yaml \
  --output /tmp/archguard-profile-1.json
uv run archguard architecture profile compile examples/architecture/simple-layered.yaml \
  --output /tmp/archguard-profile-2.json
cmp /tmp/archguard-profile-1.json /tmp/archguard-profile-2.json
shasum -a 256 /tmp/archguard-profile-1.json /tmp/archguard-profile-2.json
uv run archguard architecture profile inspect /tmp/archguard-profile-1.json
uv run archguard architecture evaluate /tmp/archguard-graph.json \
  --profile examples/architecture/simple-layered.yaml --output /tmp/archguard-report-1.json
uv run archguard architecture evaluate /tmp/archguard-graph.json \
  --profile examples/architecture/simple-layered.yaml --output /tmp/archguard-report-2.json
cmp /tmp/archguard-report-1.json /tmp/archguard-report-2.json
shasum -a 256 /tmp/archguard-report-1.json /tmp/archguard-report-2.json
uv run archguard architecture inspect /tmp/archguard-report-1.json
uv run archguard architecture violations /tmp/archguard-report-1.json
# The following evaluation intentionally exits 1.
uv run archguard architecture evaluate /tmp/archguard-graph.json \
  --profile examples/architecture/simple-layered-violating.yaml \
  --output /tmp/archguard-violating-report.json
uv run archguard architecture violations /tmp/archguard-violating-report.json --severity error
uv run archguard architecture explain /tmp/archguard-violating-report.json \
  violation:24aacf05f2985b965be06ccdad8401b68c2a23057e3a46ca8c96a0a39b9a492d
make architecture-self
```

The actual finding is rule `application-no-persistence-demo`: `module:demo.service` imports
`module:demo.repository` once at `src/demo/service.py`, line 1, column 0. The compliant profile
allows that existing architecture; the violation-demonstration profile deliberately prohibits it.
No example source was changed, imported or executed by evaluation.

## Engineering workload and Docker

Fixed workload v1, no randomness (seed null): 500 internal modules, five components, 100 rules,
1,000 import occurrences. On the final local verification run: assignment 0.047195 s;
evaluation 0.130304 s (including validation, assignment and hashing); 300 violations;
266,119 canonical report bytes. Timings vary by host and load. There is no CI time threshold,
benchmark experiment or claim of scientific performance/repair improvement.

Docker built package 0.4.0 successfully with Python 3.12.14 in the container. The final verified
local image ID is `sha256:4873519771b530499aa5fdc67bc68023fd9f01898ba524c7469a979e6a9cf588`.
Resolved base image digests: Python 3.12-slim
`sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea`, uv 0.11.32
`sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c`.
The Docker image is local; no release or Git tag was created.

## Limitations and next phase

Syntax-only graph resolution; no dynamic import/runtime guarantees. All external rules skip on
collapsed top-level names. Missing assignments can conservatively skip whole rules. Hashes ensure
internal consistency rather than cryptographic authenticity of recomputed malicious artifacts.
Callers must provide known protected roots; trusted stable output parents remain required.
The self profile cannot prove the absence of domain logic in entrypoints or all vendor dependencies.
Existing AST architecture tests remain necessary. No inference or before/after comparison exists.
Review Phase 4 before merge; only after acceptance should Phase 5 comparison design begin.

## File inventory

| Change | File |
| --- | --- |
| Created | `.archguard/architecture.yaml` |
| Modified | `.github/workflows/ci.yml` |
| Modified | `AGENTS.md` |
| Modified | `CHANGELOG.md` |
| Modified | `CITATION.cff` |
| Modified | `Makefile` |
| Modified | `README.md` |
| Created | `configs/architecture-self.yaml` |
| Created | `docs/architecture/constraint-dsl.md` |
| Created | `docs/architecture/constraint-engine.md` |
| Created | `docs/architecture/decisions/ADR-0005-versioned-constraint-dsl.md` |
| Modified | `docs/architecture/decisions/README.md` |
| Modified | `docs/architecture/integration-strategy.md` |
| Modified | `docs/architecture/overview.md` |
| Modified | `docs/development.md` |
| Created | `docs/phase-4-verification.md` |
| Modified | `docs/research/research-protocol.md` |
| Created | `docs/schemas/architecture-profile-v1.md` |
| Created | `docs/schemas/architecture-report-v1.md` |
| Created | `examples/architecture/simple-layered-violating.yaml` |
| Created | `examples/architecture/simple-layered.yaml` |
| Modified | `pyproject.toml` |
| Created | `scripts/benchmark_constraint_engine.py` |
| Modified | `src/archguard/__init__.py` |
| Modified | `src/archguard/application/ports/architecture.py` |
| Created | `src/archguard/application/services/architecture.py` |
| Created | `src/archguard/application/services/constraint_engine.py` |
| Modified | `src/archguard/application/services/graph_queries.py` |
| Created | `src/archguard/domain/architecture_profile.py` |
| Created | `src/archguard/domain/architecture_report.py` |
| Created | `src/archguard/domain/architecture_validation.py` |
| Modified | `src/archguard/domain/enums.py` |
| Created | `src/archguard/domain/graph_algorithms.py` |
| Modified | `src/archguard/entrypoints/cli/app.py` |
| Created | `src/archguard/entrypoints/cli/architecture.py` |
| Created | `src/archguard/infrastructure/architecture_profiles.py` |
| Created | `src/archguard/infrastructure/architecture_reports.py` |
| Modified | `tests/integration/test_api.py` |
| Modified | `tests/integration/test_cli.py` |
| Modified | `tests/integration/test_imports.py` |
| Created | `tests/unit/test_architecture_engine.py` |
| Modified | `tests/unit/test_ports.py` |
| Modified | `uv.lock` |
