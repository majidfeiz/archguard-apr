# V2.3 capability freeze and prospective protocol amendment

The successful operational capability probe is frozen as provider-admission evidence, not as a scientific execution. GitHub Actions run `46128268268` at head `e601a8f94a1cb038a13cf0950d3f1cbda70cc61b` produced artifact `15257130646`, whose ZIP SHA-256 is `598013cd64b2803ae49f5c26afb9734a271abb21e36bce77aa10023fc7b487dc`. Its sole JSON member has SHA-256 `8a6f9292b6c9cba66cc990d31172d47eb4aa5e97318c1aaa23cfc1d1fe68d18f` and capability fingerprint `77159d4236788c99bf0886a9108f018035bf4c55307e337fb36c1c3b595d5118`.

The probe made one provider request that was accepted, returned usage of 137 input and 76 output tokens, and cost USD 0.0014825. It accepted the strict schema with tools disabled. Patch-semantic validation was false, which is informational for this operational probe and does not contradict provider capability. The probe performed zero scientific executions and its cost is excluded from the scientific budget.

The prior scientific protocol fingerprint `7d714e14bee0acba48c72377b0a0a3e73e8dd830bc92a1949f4139858ad0268d` remains immutable. The prospective amended fingerprint is `5a110f57dc86e1b4e932bf81e5905a71da65253ab93ed2b68f323f16bd681e05`. It preserves the frozen model, schema, medium reasoning effort, tools-disabled configuration, task manifests, condition order, eight-call maximum, zero retries, USD 0.1175 per-call reservation, USD 0.9400 total reservation, and USD 1.0000 hard ceiling.

The historical provider-admission incident from run `45979876101` remains excluded from the scientific result set. It contains zero valid scientific executions and does not authorize repeating an ordinal as a retry. The amendment requires a clean, empty scientific checkpoint and represents a prospective execution under a new protocol fingerprint.

The exact amended order is:

1. PySnooper-2 / BASELINE
2. PySnooper-2 / GRAPH_ONLY
3. PySnooper-2 / GRAPH_CONSTRAINTS
4. PySnooper-2 / FULL_ARCHGUARD
5. PySnooper-3 / BASELINE
6. PySnooper-3 / GRAPH_ONLY
7. PySnooper-3 / GRAPH_CONSTRAINTS
8. PySnooper-3 / FULL_ARCHGUARD

Readiness is `READY`, with capability status `FROZEN_SUPPORTED`, no blockers, and an `EMPTY_REQUIRED` checkpoint. Execution remains separately gated by the exact token `AUTHORIZE_V2_AMENDED_MICRO_PILOT_8_CALLS_USD_1` and environment approval. This amendment and readiness record do not trigger or authorize a provider call by themselves.
