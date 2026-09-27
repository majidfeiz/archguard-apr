# Phase 7 verification

## Baseline

The authorized HTTPS fallback fetched `main` after SSH authentication failed. `FETCH_HEAD`, local
`main`, and the Phase 7 branch point were all
`3448095eed2173f22cd00c0a7be5fbffb97ef0ca`. The baseline tree was clean, package version was
`0.6.0`, all 430 tests passed, and combined coverage was 96.38%. Frozen sync, lock, Ruff format,
Ruff lint and strict mypy all passed before branch creation. No later network Git operation occurred.

## Implemented scope

Version 0.7.0 adds trusted immutable execution plans, a Docker-only backend, source-free command and
JUnit observations, deterministic functional deltas, combined architecture/functional gates,
canonical immutable artifacts, CLI commands, a controlled self-check and Docker CI. It generates no
patch, prompt, model call, agent action, architecture inference or benchmark evaluation.

## Actual local verification

Environment: macOS host, Python 3.12.13 and 3.13.13, uv 0.11.32, Docker Desktop Linux engine.

| Check | Measured result |
| --- | --- |
| Python 3.12 non-Docker suite | 464 passed; 3 Docker tests skipped until explicit image identity |
| Python 3.13 non-Docker suite | 464 passed; 3 Docker tests deselected |
| Phase 7 focused unit/CLI | 34 passed |
| Phase 7 Docker isolation | 3 passed |
| Phase 5 worktree/CLI + Phase 6 retrieval regression | 34 passed |
| Ruff format / lint | 168 files formatted; all checks passed |
| strict mypy | 99 source files; no issues |
| pre-commit | all nine hooks passed |
| statement coverage | 4194/4397, 95.38% |
| branch coverage | 870/970, 89.69% (displayed 90%) |
| combined coverage | 94.35% |
| package build | `archguard_apr-0.7.0` sdist and wheel built |
| version / doctor | 0.7.0; all required checks true, Docker executable present |
| Compose / package image | config passed; `archguard-apr:phase-7` image `cf593865…a502` |
| validation image | `sha256:d2086fc7…d9a5` built from `Dockerfile.validation` |
| self architecture | 113 modules, 7 rules, zero violations, passed |
| example plan | valid; fingerprint `d9b741f3…4377` |

Docker smoke evidence proved non-root UID, absent Docker socket, absent unallowlisted host secret,
denied external network, bounded output, timeout termination and successful cleanup. Mandatory flags
also have unit assertions for read-only root, no capabilities, no-new-privileges, CPU/memory/PID/file
size and `/tmp` bounds. Docker unavailability produces structured infrastructure evidence with no
host fallback. No `archguard-p7-*` container or extra Git worktree remained after verification.

## Controlled engineering evidence

The trusted controlled fixture ran the same JUnit plan against baseline and candidate workspaces.
Baseline target state was failed; candidate target state was passed. The delta was accepted with one
fixed test, zero regressions and no persistent/candidate-only/baseline-only test. The 1-second timeout
test terminated the container. A 10,001-byte stdout attempt set the truncation flag at the configured
128-byte capture limit.

| Artifact | Bytes | File SHA-256 |
| --- | ---: | --- |
| baseline evidence | 831 | `dcfc3f9b05e345a5e79ad580b735b1c2e41d9997f20e4f1688f59f93b371bf1f` |
| candidate evidence | 831 | `32ef31f7def541b1d0b6c573c7de874426c53de3951339ac845e973df4ea1a6a` |
| repeated candidate | 831 | `32ef31f7def541b1d0b6c573c7de874426c53de3951339ac845e973df4ea1a6a` |
| functional delta | 497 | `bb409b52285b44db24d5cb8d6c29b4cf88b37a4921bce12d8dcbb12476e771a1` |

The repeated candidate artifacts were byte-identical. These are engineering checks, not scientific
results. Temporary evidence stayed under `/private/tmp` and is not committed.

## Limitations

Docker, its daemon, kernel, runtime and trusted image are in the trusted computing base; containers
are not hardened VMs. Architecture acceptance is not functional correctness, and selected passing
tests are not complete correctness. Earlier static-analysis limitations remain. Timing is operational
telemetry, not a reproducible research conclusion. Raw logs are not persisted. GitHub Actions did not
run locally; the workflow is configured to repeat non-Docker checks on 3.12/3.13 and Docker smoke
checks on Linux.
