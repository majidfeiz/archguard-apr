# ADR-0028: Freeze Phase 13 provider configuration before execution

## Status

Accepted on 2026-10-13.

## Decision

Phase 13 uses the snapshot-pinned OpenAI model `gpt-5.4-2026-03-05` through the Responses API.
Configuration is canonical JSON bound to the frozen population and protocol. The adapter remains
narrow and stateless. Provider calls are serialized, bounded to twelve total calls, and protected by
a deterministic fail-closed cost guard using the dated official price table.

The API key is acquired only from `OPENAI_API_KEY`. Normal artifacts contain only source-free hashes,
usage counts, calculated costs, and normalized diagnostics. Offline preflight is the default; a live
preflight requires two explicit flags and is not run as part of Phase 13A implementation.

## Consequences

Missing credentials, usage, pricing, an unknown returned model, stale bindings, or unsafe output
placement blocks execution. There is no fallback model, provider switching, or outcome-based retry.
