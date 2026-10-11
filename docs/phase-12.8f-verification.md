# Phase 12.8F verification

Baseline: clean local `main` at `43ed92f26039e9cfb690440c9b2e083c9d30b7dc`, version `0.12.8`.
The validated Phase 12.8E preflight is bound to GitHub run `37627850370`, archive SHA-256
`195b319a9de6ddacd9d79a0f01a87dd65fed5324e4a92613a754be17dc8f5523`, and the prompt-supplied
manifest/registry/policy fingerprints. Candidate membership and ordering are unchanged. The frozen
PySnooper profile and pending protocol decision are unchanged.

Seven adapters cover PySnooper-1, PySnooper-3, Black-1 through Black-4, and Cookiecutter-4.
PySnooper-2 references its existing imported STABLE qualification. No adapter is unavailable. Exact
commands, selectors and dependency-file hashes derive from BugsInPy revision
`11c5f1eea954a42132cfd06bf257766a7963e0fd`; revisions and license identities bind official upstream
repositories. GitHub run `38147331854` is imported as the canonical Linux x86 PySnooper-1 result.
All three actual buggy executions passed the one exactly selected test, so the expected buggy failure
did not reproduce. Its classification is `NOT_REPRODUCIBLE`, its decision is `NOT_QUALIFIED`, and the
fixed control was correctly not required or attempted. This is a scientific result, not an
infrastructure failure, and it authorizes neither adapter mutation nor candidate replacement.

Phase 12.8F.1 replaces the v1 opaque evaluator command with allowlisted structured argv and separately
binds the upstream requirements-file identity, explicit empty-file state, declared constraint-set
fingerprint/provenance, and acquired distribution hashes. Adapter registry v2 fingerprint is
`5575f5a88934ad998bb6c0c6da415708690a783e1dc8b636db2804ed4eed3d5f`; task revisions, selectors,
candidate membership and ordering did not change.

GitHub run `37643825730` is preserved as an engineering-complete but scientifically unsuccessful run.
It reached PySnooper-1 and PySnooper-3, both before evaluator execution, and recorded two infrastructure
failures, no passing fixed control and no qualified task. It stopped under the documented rule after
more than one infrastructure failure. Its Artifact remains historical and is not imported. Review found
an unavailable preloaded-base assumption, opaque argv construction, a missing `rg` dependency that did
not fail closed, and insufficient stage diagnostics.

Local metadata inspection accessed only the four declared GitHub repositories, used no credentials,
and executed no acquired code. Git did not report wire bytes; the measured Git-object footprint was
7,385,088 bytes and maximum metadata-root disk was 18,374,656 bytes. The temporary checkouts were
removed after adapter review. No PyPI package was downloaded locally.

## Workflow

Run the remaining reviewed evaluators after merge:

```bash
gh workflow run phase-12-8f-linux-x86-qualification.yml --ref main
```

The consolidated workflow runs exactly PySnooper-3, black-1 and cookiecutter-4, serially. PySnooper-1
is not rerun after its imported result, PySnooper-2 remains prior evidence, and Batch B cannot be
started from this workflow.

The workflow explicitly pulls `python:<exact-version>` for `linux/amd64`, verifies its requested tag,
ID/digests, OS and architecture, records that identity, and builds with `--pull=false`. It uses only
GitHub, Docker Hub for the declared Python base image, and PyPI hosts declared in its log, permits
network only for Git, base acquisition and container dependency preparation, and runs evaluator
attempts with network none. It enforces 2 GiB
aggregate transfer, 8 GiB temporary disk, and 10 MiB retained Artifact ceilings. Prospective planning
for the three remaining tasks is under 700 MiB transfer, 5 GiB disk, and the 350-minute job timeout.
These are conservative pre-run bounds, not measured results. A standard-library scanner must complete
successfully before security status can be PASSED or an Artifact published; missing inputs, non-UTF-8
content, secrets, diff markers, forbidden fields and absolute runner paths fail closed.

Each run uploads exactly one flat, source-free, 14-day Artifact named
`archguard-phase-12-8f-remaining-qualification-<run-id>`. Download it outside the repository and run:

```bash
PYTHONPATH=src python scripts/phase128f_evidence.py validate --archive /path/evidence.zip
PYTHONPATH=src python scripts/phase128f_evidence.py import \
  --archive /path/evidence.zip --output research/evidence/phase-12.8f-remaining-qualification.json
```

Import requires separate review and a later commit. Implementation is not qualification evidence;
GitHub Actions must still run. Non-STABLE candidates remain scientific results. No repair experiment,
provider call, patch generation, gold inspection, local target execution, pilot freeze, or Phase 13
execution occurred. `phase_13_ready=false`.
