# Phase 15A verification

Baseline `bc12e7c5e60052e0f5399777ba3bb3f95d76f95d` was a clean `main` with Phase 13 `COMPLETED_WITH_ATTRITION`, 49-section bilingual manuscript parity, and valid publication hashes. Phase 15A prepared public documentation, scoped licenses, citation metadata, governance guidance, inventories, and release drafts without changing scientific evidence.

Security scans found no credential, private key, database URL, raw provider response, or committed restricted benchmark/gold payload. A non-public personal email was removed from the current tree but remains in four reachable commits, so the release gate is `BLOCKED` pending an explicit owner remediation decision. No history was rewritten.

Validation covers README links and offline commands, CFF/YAML/JSON/CSV syntax, publication hashes, release-manifest consistency, focused release tests, Ruff, strict mypy, and the Python 3.12 full suite. No provider call, experiment, repair agent, external benchmark, Docker workload, GitHub Actions run, remote setting change, tag, release, push, or Zenodo publication occurred.

Results: 12 focused Phase 14/15 tests passed; README offline CLI smoke commands passed; Ruff formatting and lint passed; strict mypy passed for 197 source files; JSON, YAML, CFF, CSV, lockfile, bilingual, document-structure, and manuscript-hash validation passed. The single full Python 3.12 run completed with 989 passed, 4 skipped, and 90.01% combined statement/branch coverage. An optional offline package build could not resolve uncached `hatchling`; no network access was requested, and `uv lock --check --offline` passed.
