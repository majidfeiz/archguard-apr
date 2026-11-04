# Invalid-patch root-cause audit

## Observed facts

Phase 13 planned six executions. Four reached and completed the provider; all four terminal outcomes
were `invalid_patch`. Two `black-4` executions ended before a provider call with checkout validation
failure. The four calls used 35,431 input and 2,737 output tokens and cost USD 0.1296325 under the
frozen configuration. These facts are copied from the immutable closure artifacts, not recomputed as
new experimental results.

## Unknowable from retained evidence

Raw provider responses were intentionally not retained. Therefore it is impossible to prove whether
any historical response was fenced, truncated, malformed at a particular header, unsafe by path or
mode, context-mismatched, or rejected for another exact inspector reason. No exact historical root
cause is claimed, and no historical invalid patch is reclassified.

## Implementation findings

The Phase 13 runner requested strict JSON containing only `patch`, decoded `response.output_text`,
then passed the string bytes directly to `UnifiedDiffInspector`. Inspector rejection became the
single string `patch_policy_rejection`; application failure became `patch_application_failure`.
This preserved safety but discarded stage/reason precision. The contract did not bind task and
candidate identifiers or declared paths. It had no documented fence/CRLF presentation boundary and
no source-free normalized-patch identity. The separate general provider response contract was not
the frozen Phase 13 runner's contract.

## Unsupported assumptions and regression risks

It is unsupported to assume models always emit a raw Git diff inside a JSON string, that one
`invalid_patch` cause dominated all four outputs, or that normalization alone would have produced a
correct repair. Synthetic tests must cover prose, multiple patches, malformed/truncated hunks,
unsafe paths and modes, binary/rename/copy operations, declaration mismatch, size ceilings,
application context mismatch, policy and architecture rejection, cleanup, and non-mutation.

## V2.1 changes

V2.1 adds an immutable strict response, three-form extractor, bounded normalization, exact declared
path matching, raw/normalized hashes, stable stage/reason diagnostics, author-owned offline fixtures,
and a provider-free benchmark preflight. The existing inspector and isolated worktree boundaries are
retained.

## Deferred to the paid micro-pilot

The micro-pilot must establish observed schema-valid, syntactically valid, and applicable rates;
confirm provider support for the exact schema; test the prospective retry/cost rules; and determine
whether any remaining failures cluster by stage. It cannot proceed without explicit approval and the
preflight gates passing.
