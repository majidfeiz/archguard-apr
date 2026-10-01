# Provider configuration schema v1

`archguard.provider-config/v1` is strict and immutable. It declares official provider, allowlisted
model, timeouts, output bound, bounded retry, structured-output mode, optional supported controls,
role mappings and logging/live switches. Unknown fields/providers/roles, missing mappings, embedded
credentials, custom endpoints, insecure endpoints, unbounded values and non-allowlisted models fail.
Environment placeholders are allowed only for `OPENAI_MODEL` and `ANTHROPIC_MODEL`.
