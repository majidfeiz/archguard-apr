# V2 scientific-response accounting incident

The first amended scientific run is preserved from source artifact SHA-256 `48ce91de65b207ba8791470307e71d08026cec6e8229077cd2a7712d54926b9c` and preflight artifact SHA-256 `343206a7ef5c59bdcef6e543418381c2e6aeaf60f6c976427ebd24ccbe688397`. Both archives were validated in place for exact membership, regular-file modes, safe compression, unique names, canonical source-free JSON, internal checksums, and protocol binding. The original ZIPs are not repository artifacts.

## Proven failure path

`OpenAIResponsesAdapter.invoke_v2_repair` measured provider usage before detecting an invalid post-response condition. Its `ProviderInvocationError` retained only `usage_returned=true`, not the measured usage or a safe response disposition. `V2OpenAIProvider.invoke` converted every `ProviderInvocationError` into `ProviderAdmissionFailure`. The runner consequently recorded zero accepted calls, zero tokens, and zero cost even when the provider had returned trustworthy usage.

The repaired boundary carries provider-neutral usage and one safe response state: completed, incomplete at the output limit, other incomplete, refusal, schema rejection, or not received. A trustworthy usage-bearing post-response failure becomes a charged/accepted failure, is reconciled against the reservation, and remains an infrastructure attrition rather than a completed scientific execution. Pre-provider rejection remains an unaccepted zero-cost failure. Raw responses, prompts, patches, provider messages, source, and gold material are never retained.

## Historical interpretation

The authoritative retained accounting is two request attempts, one reliably accepted provider call, one completed scientific execution, 5,291 input tokens, 2,000 output tokens, and USD 0.0432275 observed cost. Cleanup completed and fairness is `FAIR`.

Ordinal 1, PySnooper-2 / BASELINE, remains an immutable completed scientific execution classified `EXTRACTION_FAILURE`. The retained evidence does not say whether the provider response was incomplete or output-limited. Although 2,000 output tokens equals the configured maximum, that equality alone does not prove truncation.

Ordinal 2, PySnooper-2 / GRAPH_ONLY, remains historical attrition with diagnostic `SCHEMA_REJECTION` at the response stage. Its diagnostic says usage was returned, but the defective boundary discarded the values. Its provider acceptance, token counts, cost, response disposition, and response details are therefore unknown and are not reconstructed.

## Prospective continuation proposal

The old protocol fingerprint is `5a110f57dc86e1b4e932bf81e5905a71da65253ab93ed2b68f323f16bd681e05`. The check-only proposal fingerprint is `1c72398b18afa1c1b7a3958db2a79dcca338bf66d0757565bfa4c9ca98ec0daa`.

Under the proposal, ordinal 2 remains attrition and is not rerun. A future separately authorized continuation may cover only ordinals 3 through 8, with at most six additional requests, zero retries, USD 0.7050 additional reservation, and USD 0.7482275 maximum known total scientific cost. Repeating ordinal 2 would require a different prospective fingerprint and explicit future human authorization. The proposal itself is check-only and authorizes no provider or scientific execution.
