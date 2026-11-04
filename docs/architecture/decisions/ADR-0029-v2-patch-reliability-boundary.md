# ADR-0029: strict V2 repair-response and extraction boundary

Status: accepted for prospective V2 engineering; no scientific protocol approval.

## Context

Phase 13 retained source-free outcomes but not raw provider responses. All four completed outputs
were classified `invalid_patch`, so the exact historical failure mechanism cannot be reconstructed.
The live runner accepted a minimal `{patch: string}` object and sent its string directly to the
Phase 5 inspector, leaving no prospective stage-level diagnosis.

## Decision

Place an immutable provider-neutral response contract and deterministic extractor before the
unchanged strict inspector. Domain owns schemas, limits, stages, codes, and source-free identities;
application owns the extraction port and workflow; infrastructure owns UTF-8/JSON/fence decoding.
Only raw diff, one surrounding Markdown fence, and the strict structured object are supported.
Normalization is limited to removing that one fence and CRLF-to-LF conversion.

The extractor never reads a repository, applies a patch, executes content, or persists raw input.
Application and architecture evaluation remain separate later stages. Existing Phase 5 isolation,
path, mode, and patch-policy gates remain authoritative and are not weakened.

## Consequences

Future failures can be diagnosed without source disclosure. Raw and normalized SHA-256 identities
permit correlation without retaining source. Historical Phase 13 records remain immutable. The new
contract must be exercised in a paid micro-pilot before any effectiveness inference.
