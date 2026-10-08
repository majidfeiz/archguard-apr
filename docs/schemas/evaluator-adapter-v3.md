# Evaluator adapter v3

`archguard.evaluator-adapter/v3` extends v2 with buggy/fixed selector plans, evaluator source type and
provenance, installation plan, working directory, expected framework, quarantine policy, review
status, and optional evaluator-fixture path/hash. Reviewed adapters require all fields and canonical
fingerprints. Distinct selector plans require separately reviewed semantic-equivalence evidence.

Batch A uses `FIXED_REVISION_QUARANTINED_TEST`; the fixture hash binds byte-identical evaluator input
across buggy and fixed runs. Batch B remains v2 and is prohibited from the F.4 workflow.
