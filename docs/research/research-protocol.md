# Preliminary research protocol

## 1. Working title

ArchGuard-APR: Architecture-Constraint-Aware Multi-Agent Program Repair with Repository Graphs and Execution Feedback.

## 2. Problem statement

A functionally passing candidate may violate repository dependency boundaries. Investigate joint functional and architectural acceptance.

## 3. Motivation

Explicit architecture feedback could make repair review more systematic. This is a motivation, not an established effectiveness claim.

## 4. Preliminary research gap

Prior coverage and novelty remain unverified. TODO: verify primary literature before asserting a gap. No papers or findings are claimed here.

## 5. Scope

Phase 1 provides engineering and metadata foundations. Phase 2 implements deterministic local Python discovery, AST extraction and canonical snapshot persistence without executing source. Future work concerns repository-level repair. Phase 3 adds deterministic snapshot-derived graphs and structural queries. No research benchmark or agent exists yet. The 500-file script is an engineering guardrail, not experimental evidence of repair quality.

## 6. Research questions

RQ1 joint acceptance; RQ2 graph retrieval; RQ3 critique; RQ4 overhead; RQ5 component contribution. See research-questions.md.

## 7. Falsifiable hypotheses

H1 validation increases joint acceptance; H2 graph retrieval increases context recall; H3 critique reduces violations/regressions; H4 added components increase latency/tokens/cost; H5 ablation reduces joint acceptance. Corresponding nulls specify no difference.

## 8. Proposed system

Separate repository analysis, graph retrieval, architecture validation, candidate proposals and isolated execution through neutral ports. Keep external validation separate from internal orchestration.

## 9. Independent variables

Validation, retrieval strategy, critique, method variant, model/provider version, budgets and seeds. Block by repository/task and balance run order.

## 10. Dependent variables

Joint acceptance, independent functional correctness, new architecture violations, localization rank, context precision/recall, regressions, wall time, token counts and monetary cost.

## 11. Baselines

Planned: single-agent execution-feedback repair, semantic retrieval alone and external-agent repair without ArchGuard validation. Match model, context and total budget. TODO: verify implementations and versions.

## 12. Ablation variants

Full planned pipeline minus graph retrieval, architecture validation, critique or execution feedback. Prespecify interactions and account for budget changes.

## 13. Dataset-selection strategy

Audit public repository tasks for provenance, runnable environments, rights and gold-patch availability. Freeze task IDs and commits before evaluation. No dataset size is chosen.

## 14. Inclusion criteria

Reproducible failing baseline, exact revision, independently checkable outcome, compatible license and independently reviewable architecture specification.

## 15. Exclusion criteria

Unresolvable environment, unverifiable provenance, incompatible rights or required private credentials. Apply exclusions before seeing method outcomes and publish reasons.

## 16. Evaluation metrics

Primary: eligible task-run fraction with independent functional acceptance and no new forbidden architecture violation. Report functional acceptance separately, severity/counts, regressions, localization MRR and context recall. Use blinded independent labels. Count timeouts/provider failures as primary failures and report categories.

## 17. Statistical-analysis plan

Preregister primary outcome and contrasts. Use paired task comparisons, repository-cluster bootstrap confidence intervals, effect sizes and paired categorical tests where assumptions hold. Analyze skewed overhead with paired distributions. Apply Holm correction for confirmatory contrasts and label exploratory results. TODO: pilot-based power/sample-size and repetition plan; keep pilot tasks separate.

## 18. Reproducibility strategy

Record Git commit/dirty state, lock/config hashes, OS/Python/container digest, task revision, seeds, budgets, provider/model versions, UTC timestamps and artifact checksums. Archive failures and denominators. Fixed seeds do not ensure provider determinism. Exclude gold patches and hidden test answers from repair context.

## 19. Ethical considerations

Respect authors and provider terms. Minimize data transfer; redact personal data and credentials. Isolate untrusted execution, restrict network access and disclose vulnerabilities responsibly.

## 20. Licensing considerations

Code Apache-2.0; original documentation CC BY 4.0. Future original datasets require compatibility review. Preserve upstream licenses and do not redistribute unauthorized code.

## 21. Threats to validity

Construct: tests and architecture rules are incomplete proxies. Internal: model/budget drift and reviewer bias. External: repository/language selection. Conclusion: task dependence, low power and multiple testing. Mitigate through independent evaluation, blocking and preregistration.

## 22. Expected contributions

Potential deliverables: a neutral platform, controlled evaluation protocol and evidence about architecture feedback. These are expectations, not findings.

## 23. Open decisions

TODO: verified literature, languages, datasets, architectural ground truth, models, budgets, sample size, repeats, evaluators, retention and sandbox design. Resolve before confirmatory evaluation.

Record snapshot and graph schema versions, both artifact hashes, graph fingerprint, build options and partial status separately. Keep graph construction timing distinct from AST analysis. Graph cycles do not establish architecture violations or repair quality.

Phase 4 adds explicit user-authored profiles and deterministic conformance. Record profile/report
schema versions, both semantic fingerprints and raw artifact hashes, assignment policies, every rule
control and partial/skipped status. Freeze independently reviewed profiles before evaluation and
prevent gold-patch or hidden-answer leakage into specifications. Dependency violations count unique
(rule, source module, target module) groups, not import occurrences; cycle violations count scoped
cyclic SCCs per rule. Separate assignment diagnostics from rule findings. Overlapping independent
rules can each flag one dependency. Never compare aggregate counts across changed profiles without
accounting for rule/granularity changes. Self-hosting CI and the fixed 500-module engineering workload
are not benchmark experiments and provide no evidence that architecture feedback improves repair.
