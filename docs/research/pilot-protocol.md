# Pilot protocol

Mode A is deterministic CI framework verification with four synthetic tasks, seven systems and two
repetitions. Mode B is an explicitly triggered external infrastructure check without paid inference
where possible. Mode C is an explicitly authorized live LLM pilot using frozen `PILOT` tasks only.
`EVALUATION` and `EXCLUDED` tasks are rejected before materialization, indexing or provider dispatch.

Preflight must state task/configuration/repetition counts, maximum runs, calls and units, dated-price
cost range or unknown, storage, Docker executions, runtime, platform and missing prerequisites.
Suggested readiness gates, frozen before external observations, are: setup and target reproduction at
least 90%, evaluator stability 100% over repeated checks, leakage and fairness 100%, evaluation access
zero, infrastructure failures at most 10%, required metric completeness at least 95%, deterministic
aggregation/replay 100%, and zero orphans. These engineering thresholds are justified as fail-closed
minimums for a small pilot and require a new plan version if changed.
