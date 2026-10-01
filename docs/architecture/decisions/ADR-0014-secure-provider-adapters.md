# ADR-0014: Secure direct provider adapters

Status: accepted (2026-10-01).

Use direct official OpenAI and Anthropic SDK adapters behind the Phase 8 `AgentPort`. Keep capability,
error, usage and artifact contracts provider-neutral. Disable SDK retries and provider tools; validate
every result before orchestration. This avoids framework leakage and centralizes bounded retry/security
policy. Tradeoffs are two maintained adapters and explicit provider differences.
