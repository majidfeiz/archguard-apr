# Proposed V2 ablation design

The machine-readable proposal is
`research/v2/protocol/proposed-ablation-protocol.json` and remains
`PROPOSED_REVIEW_REQUIRED`. Four conditions isolate graph retrieval, architecture constraints, and
orchestration while holding model snapshot, task order, call/token/time/resource ceilings, retry
policy, and patch-validity rules constant. Analysis is paired; infrastructure attrition is separate
from repair failure.

The minimum proposed evaluation is 30 qualified tasks, preferably 50, over at least three projects,
selected outcome-blind and stratified by project. A small, explicitly approved micro-pilot precedes
population freeze. Metrics separate schema validity, diff validity, applicability, plausibility,
correctness, architecture deltas, regressions, time, tokens, cost, and attrition.

The proposed micro-pilot has a USD 1.00 hard ceiling, reserved-cost accounting before every request,
no automatic continuation, and no retry unless prospectively allowed. No provider call is enabled by
this document or by preflight.
