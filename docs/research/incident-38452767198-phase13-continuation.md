# Phase 13 continuation incident 38452767198

Execution 1 (`PySnooper-2 / baseline`) produced a valid `invalid_patch` scientific outcome. The old
runner retained that result but later stopped the experiment when ordinal 2 failed before provider
transmission. Its reservation-time accounting incorrectly reported two calls even though the CLI,
the sole completed usage record, and the network-attempt evidence establish one provider call.

The canonical checkpoint preserves execution 1, its token usage, USD 0.025945 cost, and outcome
without alteration. The repair changes only orchestration continuation, checkpoint integrity, and
provider-call accounting. It makes no outcome-aware prompt or evaluator change. Ordinal 1 is an
immutable completed prefix and will not be scheduled again; continuation begins at ordinal 2.
