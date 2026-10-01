# Provider parity

| Concern | OpenAI | Anthropic |
| --- | --- | --- |
| Endpoint | Responses | Messages |
| Structure | strict `text.format` JSON Schema | forced strict client tool |
| Refusal | refusal content item | `stop_reason=refusal` |
| Incomplete | response status/details | stop reason |
| Usage | input/output/cache/reasoning when reported | input/output/cache/thinking when reported |
| Request ID | response ID | SDK public `_request_id` |
| Timeout/retry | bounded timeout; SDK retry off | bounded timeout; SDK retry off |
| Stateless/data | `store=false`; account controls still apply | stateless Messages request |
| Tools | none | exactly one non-executing result tool |

Capabilities are deliberately not claimed equal. Anthropic uses tool-shaped output in this adapter;
OpenAI uses direct structured text. Provider inference, availability, rate limits and retention terms
remain provider/account dependent.
