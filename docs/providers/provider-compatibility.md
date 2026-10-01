# Provider documentation compatibility

Accessed 2026-10-01. Implementation follows documented public API/SDK contracts, not SDK internals.

## OpenAI

- Responses migration and `text.format`: https://developers.openai.com/api/docs/guides/migrate-to-responses
- Structured Outputs, schema limits, refusals and incomplete output: https://developers.openai.com/api/docs/guides/structured-outputs
- Responses API reference: https://developers.openai.com/api/reference/resources/responses/methods/create
- Error codes: https://developers.openai.com/api/docs/guides/error-codes
- Data controls and `store=false`: https://developers.openai.com/api/docs/guides/your-data
- Python SDK: https://github.com/openai/openai-python

The adapter uses Responses, strict JSON Schema, no tools, bounded client timeouts and disabled SDK
retries so ArchGuard owns retry semantics. `store=false` requests stateless operation but is not a
claim of zero retention. Availability and supported controls vary by model, account and project.

## Anthropic

- Messages API: https://platform.claude.com/docs/en/api/messages/create
- Structured outputs: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- Tool use: https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview
- Stop reasons: https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons
- Errors and request IDs: https://platform.claude.com/docs/en/api/errors
- Rate limits and retry guidance: https://platform.claude.com/docs/en/api/rate-limits
- Python SDK, retries and timeouts: https://platform.claude.com/docs/en/api/sdks/python

The adapter uses one forced, allowlisted client tool with strict `input_schema`; it rejects all
other tool names and conflicting calls. SDK retries are disabled so one bounded policy owns retries.
Model access varies by account. No Bash, editor, computer, web, repository or execution tool is sent.
