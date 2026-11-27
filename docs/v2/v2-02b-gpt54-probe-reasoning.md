# V2.2 GPT-5.4 capability-probe reasoning incident

The second separately authorized operational probe was rejected at provider admission before usage
was returned. It was not an accepted provider call or a scientific execution. The source-free
identity is recorded in `v2-02b-provider-reasoning-incident.json`; it does not establish that the
frozen model processed the request.

The retained safe metadata proves HTTP status `400`, provider code `unsupported_value`, failure kind
`INVALID_REQUEST`, stage `request`, no returned usage, and a non-retryable result. Inspection found
that the probe requested reasoning effort `minimal`, which frozen model `gpt-5.4-2026-03-05` does
not support. Its frozen supported set is `none`, `low`, `medium`, `high`, and `xhigh`.

Only the operational probe changes to `none`. The eight-call scientific configuration remains
`medium`. Model-specific settings now fail locally if a reasoning value is outside the frozen table.
The next probe requires the new token
`AUTHORIZE_V2_PROVIDER_CAPABILITY_PROBE_REASONING_FIX_1_CALL`; neither earlier token is accepted.
