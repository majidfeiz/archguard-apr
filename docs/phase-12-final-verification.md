# Phase 12 final verification

Phase 12 is closed under the approved **Exploratory Multi-Project Feasibility Protocol**. The frozen
Linux x86_64 population is `PySnooper-2`, `PySnooper-3`, and `black-4`: three qualified/stable tasks
across PySnooper and Black. Five other selected tasks remain visible and excluded.

| Task | Final result | Evidence/run |
|---|---|---|
| PySnooper-1 | NOT_QUALIFIED / NOT_REPRODUCIBLE | `477bc32a…` / 38147331854 |
| PySnooper-2 | QUALIFIED / STABLE | `a3a361ae…` / 37009930401 |
| PySnooper-3 | QUALIFIED / STABLE | `f975e236…` / 38149905317 |
| black-1 | NOT_QUALIFIED / EVALUATOR_ENVIRONMENT_INVALID | `f975e236…` / 38149905317 |
| black-2 | NOT_QUALIFIED / EVALUATOR_ENVIRONMENT_INVALID | `d9d58d8d…` / 38221805148 |
| black-3 | NOT_QUALIFIED / EVALUATOR_ENVIRONMENT_INVALID | `d9d58d8d…` / 38221805148 |
| black-4 | QUALIFIED / STABLE | `d9d58d8d…` / 38221805148 |
| cookiecutter-4 | NOT_QUALIFIED / EVALUATOR_ENVIRONMENT_INVALID | `f975e236…` / 38149905317 |

The qualification registry fingerprint is `4b47b4c4b3042a572ff5e91969defbc25c3decd22b7a3fec0b0aae873586a1b3`.
Population, protocol, and approval fingerprints are respectively
`421f3129ef6bee5883c41d05f087d6faff5b2a3de3b2ea543b4d27ade1488886`,
`93494690f402d17e511d9cad1fdc92907d408ae3a923139d30537894f9ab8ce7`, and
`2ff4adc5be719608860845d68be15c07205bf563423099a30c617e3d29170d7d`. The prior pending decision is
preserved by SHA-256 in the approval audit chain.

All scientific preparation gates are satisfied. `PROVIDER_NOT_CONFIGURED` is the only remaining
operational blocker: no provider, model, price, key, or monetary approval was invented. This small,
attrited, project-concentrated population supports descriptive feasibility claims only; Black has no
separately frozen project architecture profile.

After prospective provider/model/cost approval is recorded and frozen, re-run
`uv run archguard readiness gate --facts research/readiness-facts.json`; do not start Phase 13 before
that operational gate passes.
