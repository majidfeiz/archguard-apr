# Public-release security audit

Audit baseline: `bc12e7c5e60052e0f5399777ba3bb3f95d76f95d`. Scope: the tracked tree and all reachable commits. The scan was read-only; `gitleaks` was not installed, so repository-native filename-only regular-expression scans were used. Sensitive candidate values were never printed or copied into this report.

## Findings

| Scope | Category | Location | Finding |
|---|---|---|---|
| tree | credentials/private keys/database URLs | — | none detected |
| history | credentials/private keys/database URLs | — | none detected |
| tree | historical personal email | decision records only | `ACCEPTED_PERSONAL_DISCLOSURE`; scoped author authorization recorded |
| history | historical personal email | redacted fingerprint begins `15daf06c3db8` | `ACCEPTED_PERSONAL_DISCLOSURE`; not a credential, secret, incident, private key, or release blocker |
| tree/history | host-path strings | defensive validators, CI sanitizer, and tests | literals only; no actual user path disclosed |
| tree | authorization value | `tests/unit/test_logging.py` | explicit synthetic redaction fixture |
| tree/history | raw provider payload | — | none detected |
| tree/history | committed gold/reference patch payload | — | none detected; matches were policies, validators, and synthetic negative tests |

Majid Feiz Deilami accepted public disclosure of the author-owned historical personal email in the scoped [machine-readable](../../release/decisions/personal-email-disclosure.json) and [human-readable](../../release/decisions/personal-email-disclosure.md) decisions. This is an author risk decision, not a legal opinion, and it does not extend to any secret, credential, private third-party data, provider response, or restricted benchmark content. Git history was not rewritten.

The distribution-boundary review found no redistributed benchmark repository or source archive, benchmark gold/reference patch, SWE-bench dataset payload, BugsInPy source payload, evaluator-only restricted material, third-party font, third-party paper, or raw provider output. External benchmark and dataset rights remain limitations for material referenced but not redistributed; they are not repository-publication blockers. The release gate is `READY_FOR_PUBLICATION` because no real security, licensing, integrity, citation, or restricted-data blocker remains.

Ignored local caches, virtual environments, coverage output, build output, `.env` files, credentials, model output, benchmark checkouts, worktrees, gold quarantine, evaluator-only data, and patch files remain excluded. GitHub secret scanning and push protection should be enabled before accepting public contributions.
