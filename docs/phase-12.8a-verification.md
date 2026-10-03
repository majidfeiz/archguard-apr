# Phase 12.8A verification

Status: `EXTERNAL_EXECUTION_REQUIRED` and `REVIEW_REQUIRED`; `phase_13_ready=false`.

Baseline: `2bfaf421999f355cd7d523003ca6e3e1ee5c8038` on `main`, version `0.12.8`.

Baseline is recorded at implementation time. Local preparation creates separate source-free license,
graph-evidence, candidate, pilot, and power/design artifacts. No external source was acquired or run,
no GitHub Actions workflow was claimed as executed, and no human decision was changed.

Current license registry: four records, zero `VERIFIED`, four `UNRESOLVED`, zero `INELIGIBLE`.
PySnooper has an immutable license-file hash but no locally reviewed SPDX decision. BugsInPy remains
unresolved because no license file was observed at its pinned revision. SWE-bench framework and dataset
remain separately unresolved. These are research eligibility decisions, not legal advice.

The outcome-blind candidate pool contains one metadata-supported task from one project; it is not
eligible while framework licensing is unresolved. The selected pilot is empty. The final population is
not frozen. PySnooper graph evidence remains `EXTERNAL_EXECUTION_REQUIRED`; the profile fingerprint is
unchanged and its existing decision remains pending.

Exact McNemar scenarios show why 4–6 tasks are feasibility-only: under the recorded assumptions, power
ranges from 0.039–0.243 at 20 tasks, 0.077–0.409 at 30, and 0.147–0.656 at 50. The proposed v2 protocol
therefore recommends at least 30 and preferably 50+ tasks subject to prospective review. Provider use and
cost remain disabled/unknown.

Stable local blocker categories are `INSUFFICIENT_CANDIDATE_POOL`, `PILOT_SELECTION_NOT_READY`,
`GRAPH_EVIDENCE_EXTERNAL_EXECUTION_REQUIRED`, `INSUFFICIENT_QUALIFIED_TASKS`,
`INSUFFICIENT_PROJECT_DIVERSITY`, `TASK_LIST_NOT_FROZEN`, `LICENSES_UNVERIFIED`,
`ARCHITECTURE_ANALYSIS_INCOMPLETE`, `PROFILE_REVIEW_REQUIRED`, `PROTOCOL_REVIEW_REQUIRED`, and
`PROVIDER_NOT_CONFIGURED`.

Local Python 3.12.13 verification: 653 passed, 3 skipped, 3 warnings, 91.33% combined
statement/branch coverage; focused Phase 12.8/12.8A tests 52 passed with one expected duplicate-ZIP
construction warning. Ruff, strict mypy, canonical fingerprint validation, and unchanged pending-review
checks passed. Python 3.13, external workflows, actionlint, and shellcheck were not run locally.
