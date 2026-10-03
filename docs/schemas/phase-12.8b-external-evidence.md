# Phase 12.8B external evidence

The Phase 12.8B ZIP is a source-free transport with exactly nine root members:
`manifest.json`, `acquisition-summary.json`, `license-evidence.json`, `graph-evidence.json`,
`graph-determinism.json`, `security-scan-summary.json`, `cleanup-summary.json`,
`readiness-summary.json`, and `SHA256SUMS`.

JSON members use sorted-key compact UTF-8 JSON with a trailing LF. `SHA256SUMS` covers every JSON
member. The validator rejects extra or nested paths, duplicates, traversal, symlinks, binary content,
oversized members, noncanonical JSON, bad hashes, revision/profile mismatches, and any assertion that
Phase 13 is ready.

The manifest schema is `archguard.phase-12.8b-evidence-manifest/v1`. It binds the PySnooper-2 task,
the exact framework/buggy/fixed revisions, acquisition/license/graph/profile fingerprints, GitHub run
metadata, and `phase_13_ready=false`. License records distinguish project, framework, and dataset
scope. `UNRESOLVED` is valid evidence and remains a scientific blocker.

Validate or import a downloaded archive without executing target code:

```console
uv run archguard readiness phase128b validate --archive evidence.zip
uv run archguard readiness phase128b import --archive evidence.zip --output /tmp/phase-12.8b-import
```
