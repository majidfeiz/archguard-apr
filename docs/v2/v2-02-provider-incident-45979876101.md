# V2.2 provider-admission incident 45979876101

## Status

Historical and immutable. This document does not reclassify, repair, or replace the archived
artifact and does not authorize another provider request.

## Preserved facts

- GitHub Actions run: `45979876101`
- Outer source-free artifact SHA-256:
  `0e19fc60fc6712593b5707411c17636fa1aa0ac66b607f37fa67a779be3d7db4`
- Inner evidence ZIP SHA-256:
  `d3768af27350654fc628d15b6d3fdf572bdd20de3a0bf2129b57b721d404fce6`
- Attempted ordinal: 1, `PySnooper-2 / BASELINE`
- Provider request attempts: 1
- Trustworthy usage: 0 input tokens, 0 output tokens
- Observed provider cost: USD 0.00
- Historical diagnostic fingerprint:
  `77b4bcefbca3b53611661de17a1529ccc27537aba4edfe8a0d9c286abb01bf8d`
- Completed scientific executions: 0
- Remaining ordinals attempted: none
- Cleanup: complete

## Root cause and limits

The V2.2 adapter caught every provider exception and converted it to a charged failure with zero
usage. The runner then reconciled that value through the same method used for successful provider
responses, which appended ordinal 1 to `completed_ordinals`. This collapsed request attempts,
accepted/charged calls, scientific completions, and provider-admission failures into one state.

The historical evidence retained only a diagnostic fingerprint, zero usage/cost, and source-free
aggregate state. It intentionally did not retain a raw provider response, exception, HTTP body,
headers, request, or message. Consequently, the original detailed provider failure category,
HTTP status/code, stage details, and request identifier are unrecoverable. No category is inferred
retrospectively.

## Resume disposition

The incident is a provider-admission attempt, not a completed scientific execution. Its ordinal
also cannot be silently repeated: a repeat of ordinal 1 requires a prospective protocol amendment
with a new fingerprint and explicit authorization. The legacy checkpoint is therefore preserved
as historical evidence but is not accepted as a resumable V2 checkpoint.
