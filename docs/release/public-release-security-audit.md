# Public-release security audit

Audit baseline: `bc12e7c5e60052e0f5399777ba3bb3f95d76f95d`. Scope: the tracked tree and all 148 reachable commits. The scan was read-only; `gitleaks` was not installed, so repository-native filename-only regular-expression scans were used. Values were never printed or copied into this report.

## Findings

| Scope | Category | Location | Finding |
|---|---|---|---|
| tree | credentials/private keys/database URLs | — | none detected |
| history | credentials/private keys/database URLs | — | none detected |
| tree | non-public personal email | `paper/manuscript/manuscript-decisions.json` | removed from the current tree; SHA-256 fingerprint begins `15daf06c3db8` |
| history | non-public personal email | same path in commits `800233b9ac16`, `8be27181cf75`, `9b0212e4baa1`, `bc12e7c5e600` | remains reachable; owner remediation decision required |
| tree/history | host-path strings | defensive validators, CI sanitizer, and tests | literals only; no actual user path disclosed |
| tree | authorization value | `tests/unit/test_logging.py` | explicit synthetic redaction fixture |
| tree/history | raw provider payload | — | none detected |
| tree/history | committed gold/reference patch payload | — | none detected; matches were policies, validators, and synthetic negative tests |

The current tree is suitable for continued review, but reachable history contains information the owner explicitly marked non-public. The release gate is therefore `BLOCKED`. No history was rewritten. Before publication, the owner must choose between accepting that disclosure or performing a coordinated history rewrite and credential/privacy review; rewriting published history can invalidate clones and signatures and is outside Phase 15A.

Ignored local caches, virtual environments, coverage output, build output, `.env` files, credentials, model output, benchmark checkouts, worktrees, gold quarantine, evaluator-only data, and patch files remain excluded. GitHub secret scanning and push protection should be enabled before accepting public contributions.
