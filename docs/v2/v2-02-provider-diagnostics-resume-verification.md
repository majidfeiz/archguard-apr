# V2.2 provider diagnostics and resume verification

## Corrected state model

The checkpoint schema separately records provider request attempts, accepted provider calls,
completed scientific ordinals, and infrastructure/provider-admission failures. A zero-usage,
zero-cost provider rejection increments only the attempt and infrastructure-failure counters. A
charged failure requires positive trustworthy usage and cost, but still does not complete its
scientific ordinal.

Any failed attempted ordinal blocks continuation. Repeating it requires a prospective protocol
amendment and new fingerprint; it is never represented as an automatic retry. Completed ordinals
remain a gap-free prefix and cannot be repeated. Provider request attempts remain bounded by the
eight-call ceiling and continue to participate in reservation admission.

## Source-free diagnostics

The stable taxonomy covers authentication, permission/model access, invalid request,
structured-output/schema rejection, rate limit, network/transport, server error, and unknown
provider failure. Evidence may contain only the taxonomy value, stage, retryable flag, sanitized
HTTP status/code, usage-returned flag, and a hash of a syntactically safe request identifier.
Provider text, responses, prompts, source, patches, credentials, headers, and request bodies are
not persisted.

## Resume and capability-probe boundaries

Resume requires explicit import of one flat, allowlisted, checksum-verified source-free evidence
ZIP. Schema, canonical framing, fingerprint, ordinal order, counter consistency, duplicates, and
failure records are validated before execution. Legacy or contradictory checkpoints fail closed.

The provider capability probe is a separate one-request operational workflow. It uses the frozen
model, Responses API, strict response schema, disabled tools, zero retries, a 128-output-token
limit, and a USD 0.0050 ceiling. It records zero scientific executions and is not included in the
eight primary calls. It requires the distinct authorization phrase
`AUTHORIZE_V2_PROVIDER_CAPABILITY_PROBE_1_CALL`. That first-probe token is historical and is not
accepted by the schema-fix probe described in `v2-02a-openai-schema-compatibility.md`.

## Historical boundary

Run `45979876101`, Phase 13, and all earlier V2 evidence remain unchanged. The detailed category
for the historical provider failure cannot be recovered from its source-free fingerprint and is
reported as unknowable rather than inferred.
