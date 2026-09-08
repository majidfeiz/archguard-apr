# ADR-0010: Model-neutral byte and line budgets

Status: accepted.

UTF-8 bytes, physical source lines, file count, symbol count and excerpt count are authoritative
limits. Selection follows deterministic rank order, skips candidates that do not fit, records every
decision, merges overlapping ranges, and never splits a code point or source line. File bytes are
conservatively charged once per selected file; incremental line ranges are charged once. No model
tokenizer or provider-specific budget participates in selection.
