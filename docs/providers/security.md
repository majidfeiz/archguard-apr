# Provider security and prompt-injection threat model

Repository text, issue text, comments, patches, test output and source excerpts are delimited as
untrusted data. They cannot redefine roles, grant capabilities, enable tools or disable validation.
Provider output is validated against `AgentResponse`, role capabilities and allowed actions. Unknown
tools and validation-bypass actions are rejected.

Credentials are environment-only and excluded from configuration, fingerprints, logs and artifacts.
Normal invocation artifacts contain hashes, references, normalized status and usage—not prompts,
source, headers, raw bodies or hidden reasoning. Prompt/response logging defaults off.

These controls reduce prompt-injection risk; they are not a proof of security. Sensitive source still
requires explicit Phase 6 authorization. Models never receive shell, Git, Docker, filesystem, web,
code execution, MCP or provider-hosted search tools.
