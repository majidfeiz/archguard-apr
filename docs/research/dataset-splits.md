# Dataset splits and pilot sampling

Splits are `DEVELOPMENT`, `PILOT`, `EVALUATION`, and `EXCLUDED`. The manifest records seed, version,
grouping and frozen state. The v1 policy hashes `seed:project` into a deterministic assignment, keeping
project variants together. Reassignment requires a new version. Evaluation tasks cannot tune prompts
or policy and must be frozen before Phase 13.

Pilot selection is seeded and project-stratified before filling remaining capacity. Later adapters may
add preregistered strata (failure type, patch-size category, module count, complexity, runtime, Python
version and issue age). Gold-derived size metadata stays quarantined. Targets of ten tasks per external
benchmark are aspirations; Phase 11 reports zero externally eligible tasks because none were acquired.
