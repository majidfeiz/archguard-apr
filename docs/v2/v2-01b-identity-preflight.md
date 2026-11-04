# V2.1B PySnooper-2 identity preflight

This phase prepares an identity-only evidence boundary. It does not fetch PySnooper, call a model,
execute target code, inspect source, or run a scientific experiment. The manual workflow is the only
future acquisition path and is not triggered by this phase.

The workflow `V2.1B PySnooper-2 Fixed-Tree Identity` hard-codes the official HTTPS repository and
fixed revision. It creates a temporary bare Git object database outside the ArchGuard checkout,
fetches only that revision, resolves its commit and root tree, and internally hashes/counts the raw
`git ls-tree -r -z` stream. It performs no checkout, worktree creation, source opening, hook,
submodule, LFS, dependency installation, target execution, or provider call. Acquisition is bounded
at 64 MiB and all temporary objects are removed before the evidence archive is built and uploaded.

After an authorized maintainer runs the workflow, download its single artifact and extract the
contained `evidence.zip`. Validate and import it with:

```bash
uv run archguard experiment v2 identity validate --archive evidence.zip
uv run archguard experiment v2 identity import --archive evidence.zip \
  --output research/v2/evidence/pysnooper-2-fixed-tree-identity.json
```

Import is idempotent for byte-identical evidence and rejects a contradictory existing destination.
Importer availability does not change readiness. The V2 readiness generator may consume a future
valid imported record, but must fail closed if it contradicts the frozen task manifest.

A matching Git tree identity proves content identity for the referenced Git object. It does not
establish correctness, safety, license ownership, or successful repair.
