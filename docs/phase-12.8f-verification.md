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
repositories. PySnooper-1 remains NOT_REPRODUCIBLE unless a consistency run agrees; contradiction
records `EVIDENCE_CONFLICT_REVIEW_REQUIRED` and cannot qualify it.

Local metadata inspection accessed only the four declared GitHub repositories, used no credentials,
and executed no acquired code. Git did not report wire bytes; the measured Git-object footprint was
7,385,088 bytes and maximum metadata-root disk was 18,374,656 bytes. The temporary checkouts were
removed after adapter review. No PyPI package was downloaded locally.

## Workflow

Run Batch A after merge:

```bash
gh workflow run phase-12-8f-linux-x86-qualification.yml --ref main -f task_id=batch-a
```

Inputs are `batch-a` (default), `batch-b`, any of the seven adapter task IDs, or `all`. `all` also
requires `confirm_all_adapters_preflighted=true`. Batch A is PySnooper-1 consistency, PySnooper-3,
black-1 and cookiecutter-4. Batch B is black-2, black-3 and black-4. Execution is serial. PySnooper-2
appears through prior evidence and is not rerun.

The workflow uses only GitHub and PyPI hosts declared in its log, permits network only for Git and
container dependency preparation, and runs evaluator attempts with network none. It enforces 2 GiB
aggregate transfer, 8 GiB temporary disk, and 10 MiB retained Artifact ceilings. Prospective Batch A
planning is under 700 MiB transfer, 5 GiB disk, and the 350-minute job timeout; Batch B is under
900 MiB transfer, 6 GiB disk, and the same timeout. These are conservative pre-run bounds, not measured
results. A required Python base image must already exist on the GitHub runner; the workflow does not
access an unapproved container registry. Absence is recorded as infrastructure failure.

Each run uploads exactly one flat, source-free, 14-day Artifact named
`archguard-phase-12-8f-qualification-<selection>-<run-id>`. Download it outside the repository and run:

```bash
PYTHONPATH=src python scripts/phase128f_evidence.py validate --archive /path/evidence.zip
PYTHONPATH=src python scripts/phase128f_evidence.py import \
  --archive /path/evidence.zip --output research/evidence/phase-12.8f-qualification.json
```

Import requires separate review and a later commit. Implementation is not qualification evidence;
GitHub Actions must still run. Non-STABLE candidates remain scientific results. No repair experiment,
provider call, patch generation, gold inspection, local target execution, pilot freeze, or Phase 13
execution occurred. `phase_13_ready=false`.
