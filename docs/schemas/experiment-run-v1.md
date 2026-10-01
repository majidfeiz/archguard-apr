# Experiment Run v1

`archguard.experiment-run/v1` identifies a plan/configuration/task/repetition/model/prompt/snapshot and
references repair, candidate, evaluator, metrics and telemetry artifacts. It stores completion and
failure classification plus retry history, but never credentials, source, prompts, hidden tests or gold.
Completed run artifacts are immutable; changed stable inputs produce a new run identity.
