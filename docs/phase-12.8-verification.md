# Phase 12.8 verification

Baseline `8db89df81afa72f8af87d751383304771c3d45ea` on macOS/Python 3.12.13: 601 passed,
3 skipped, 2 warnings, 91.50% combined statement/branch coverage. Frozen dependency synchronization was
blocked by unavailable network/cache; the existing locked environment was used for the baseline.

Phase 12.7 artifact ingestion is pending because the ZIP is not present. Expected SHA-256:
`8d3d261e368a1c6bd585f33065cdcda39e4a1924f52ef9763a144d9559f8a498`. Validate/import with:

```console
archguard readiness evidence validate --archive /absolute/path/to/artifact.zip
archguard readiness evidence import --archive /absolute/path/to/artifact.zip --output research/evidence/phase-12.7-x86.json
```

The importer enforces a byte limit and exact file allowlist and rejects hash mismatch, traversal,
absolute/non-flat names, duplicate names, symlinks/devices/directories, oversized or high-ratio members,
binary/non-UTF-8 content, missing fields, inconsistent revisions, nonmatching runs, failed fixed control,
wrong platform, incomplete quarantine/cleanup, and a failed conclusion.

Candidate selection currently contains zero candidates: BugsInPy framework licensing remains unresolved,
and SWE-bench payload acquisition is prohibited in this phase. This is not a negative benchmark result.
The PySnooper draft profile and protocol decisions are pending. Thus the factual Phase 13 gate is false.

The repository follows its established major-tag Actions policy (`actions/checkout@v6`,
`actions/upload-artifact@v4`, `astral-sh/setup-uv@v6`); these are not immutable commit pins, which is a
supply-chain limitation. Workflows do not claim local GitHub Actions execution.
