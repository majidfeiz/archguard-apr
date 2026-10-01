# Statistical decision review proposal

Status: `PROPOSED`; human review required. Unit: benchmark task, with configuration outcomes paired by
task and repetitions clustered within task. Candidate binary method: exact McNemar when discordant
counts are small, otherwise preregistered McNemar plus task-cluster paired bootstrap; effect is paired
proportion difference with matched odds ratio where defined. Candidate continuous method: median paired
difference, Wilcoxon only after assumptions, and rank-biserial effect. Proposed bootstrap seed is 13025
with 10,000 task-cluster resamples; confirmatory family is C1–C0 and C1–C2…C6 with Holm adjustment.

Primary intention-to-run retains scheduled denominators and never makes infrastructure failure success;
valid-run sensitivity is separate. Benchmark-family strata are prespecified descriptive/sensitivity
views. Sample size/precision remains unassessed because zero real tasks are qualified. These choices
must not be frozen based on favorable pilot outcomes.
