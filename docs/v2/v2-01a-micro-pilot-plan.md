# V2.1A micro-pilot plan

Status: `V2_MICRO_PILOT_BLOCKED`. This is an engineering feasibility micro-pilot, not an
effectiveness study.

The frozen order is PySnooper-2 then PySnooper-3; within each task: `BASELINE`, `GRAPH_ONLY`,
`GRAPH_CONSTRAINTS`, `FULL_ARCHGUARD`. There is one execution per pair, eight maximum primary calls,
zero retries, no replacement, no outcome-based continuation, and no parallel calls.

All conditions use OpenAI Responses API model snapshot `gpt-5.4-2026-03-05`, reasoning effort
`medium`, strict `archguard.repair-response/v2.1`, 35,000 maximum input tokens, and 2,000 maximum
output tokens. All provider-side tools are disabled. Repository commands and candidate execution
remain local and sandboxed.

Worst-case admission uses uncached input pricing: USD 0.0875 input plus USD 0.0300 output equals USD
0.1175 per call. Eight reservations total USD 0.9400 under the absolute USD 1.0000 ceiling. Every
call requires prior reservation and provider-reported usage reconciliation. A missing or
contradictory usage record, retry, ninth call, or ambiguous state stops execution.

The task manifests bind frozen revisions, licenses, qualification evidence, evaluator/profile
fingerprints, sandbox policy, resources, gold quarantine, and source-free evidence. They distinguish
historical qualification from V2.1A static validation. No new external qualification occurred.

The manual workflow defaults to preflight-only. Future execution additionally requires the exact
confirmation phrase, a true blocker-free readiness artifact, and GitHub Environment approval. The
API key is available only to the execution job. While readiness is blocked, the execution step exits
before any provider client is invoked.
