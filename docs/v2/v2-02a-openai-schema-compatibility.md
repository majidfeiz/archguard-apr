# V2.2 OpenAI strict-schema compatibility incident

The separately authorized operational capability probe was rejected before usage was returned.
It was not accepted as a provider call and was not a scientific execution. The immutable source-free
identity is recorded in `v2-02a-openai-schema-incident.json`; the outer artifact ZIP is deliberately
not committed.

The retained safe provider metadata now proves HTTP status `400`, provider code
`invalid_json_schema`, failure kind `INVALID_REQUEST`, stage `request`, no returned usage, and a
non-retryable result. This evidence does not imply that the frozen model processed the request.

## Root cause and repair

The V2.1 provider schema used JSON Schema `const` for `schema_version`. The OpenAI strict Structured
Outputs subset rejected that schema at request admission. The provider-neutral V2.1 response
contract is unchanged; the provider representation now uses a typed singleton string `enum`.

One deterministic builder owns the V2.1 provider schema. Both the eight-call scientific adapter and
the operational capability probe reach that same builder. Strict mode, required fields,
`additionalProperties: false`, the nullable rationale, and array-of-string changed paths remain
unchanged. An offline fail-closed validator rejects unsupported composition and unbounded or
optional object shapes before provider access.

## Authorization boundary

The prior probe authorization is not reusable. A future verification requires the distinct token
`AUTHORIZE_V2_PROVIDER_CAPABILITY_PROBE_SCHEMA_FIX_1_CALL`. It remains one operational request,
zero retries, no tools, frozen model `gpt-5.4-2026-03-05`, USD 0.0050 maximum, and zero scientific
executions. This change does not authorize the eight-call scientific protocol.
