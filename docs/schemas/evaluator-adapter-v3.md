# Evaluator adapter v3

`archguard.evaluator-adapter/v3` extends v2 with buggy/fixed selector plans, evaluator source type and
provenance, installation plan, working directory, expected framework, quarantine policy, review
status, and optional evaluator-fixture path/hash. Reviewed adapters require all fields and canonical
fingerprints. Distinct selector plans require separately reviewed semantic-equivalence evidence.

Batch A uses `FIXED_REVISION_QUARANTINED_TEST`; the fixture hash binds byte-identical evaluator input
across buggy and fixed runs. Batch B remains v2 and is prohibited from the F.4 workflow.

Phase 12.8F.4.1 requires a named runtime consumer for every v3 field. A reviewed/available adapter
fails closed if any field is ignored. Per-task execution-plan evidence records full adapter identity,
selector, fixture, installation-plan, working-directory and mount-destination fingerprints, framework,
expected outcomes, preflight collection and container-visible fixture identity. The evaluator is
mounted at `/evaluator`, never below `/workspace`. Display abbreviations are non-authoritative.
