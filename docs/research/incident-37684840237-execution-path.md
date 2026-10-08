# Incident: Run 37684840237 fixed execution path

All four Batch A tasks reached fixed test execution and exited 1. The artifact recorded fixed outcomes
as `EXPECTED_FAILURE`, contrary to their `EXIT_ZERO` contract. Three tasks also had equal buggy/fixed
failure signatures. Zero tasks qualified; the artifact remains historical, non-imported evidence.

Local code audit proved that result normalization inherited buggy expectation semantics. It did not
prove buggy-source reuse: the evaluator image was dependency-only and runtime mounted the supplied
checkout. F.3 therefore repairs the proven semantic defect and adds source-free identity checks that
will make any future checkout, image-cache, mount or working-directory substitution fail closed.

No revision or adapter fingerprint changed. No Batch B or Phase 13 execution occurred.
