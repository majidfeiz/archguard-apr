# Comparison fairness

`archguard.comparison-contract/v1` freezes snapshot, split, sorted task IDs, configurations, provider,
model/revision, prompts, context/output/candidate/round budgets, timeout, image, profiles, repetitions,
seed and orders, retry, missing/cost policies, tests, hardware and metrics. C2–C6 must differ from C1
in exactly their declared component. C0 is a separately declared baseline, not an ablation. Any
unpermitted difference makes `comparable=false`; such a run cannot support a comparison label.
