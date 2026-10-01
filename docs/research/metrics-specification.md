# Metrics specification

No metric is calculated in Phase 11. For binary task metrics, the numerator is eligible evaluated tasks
meeting the predicate and the denominator is all eligible tasks with a non-infrastructure outcome;
missing outcomes are reported separately and never treated as success. Report task-level results and
project-clustered aggregates; repetitions aggregate within task before across-task summaries.

Repair effectiveness records resolved, target tests fixed, regressions, architecture acceptance/new
violations, candidates, rounds, valid-candidate rate and applicable-patch rate. Patch properties record
files and lines added/deleted, size, architecture-sensitive changes and protected-path rejections.
Efficiency records wall time as telemetry, provider calls/input/output units, dated-price estimated
cost, validations, Docker runs, context size and graph nodes/edges. Robustness records timeout,
infrastructure failure, malformed response, duplicate candidate and nondeterministic baseline rates.
Counts use sum; rates expose numerator and denominator; durations/costs use median, quartiles and total.
