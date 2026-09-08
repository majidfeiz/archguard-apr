# ADR-0009: Deterministic graph retrieval and explainable scoring

Status: accepted.

Use validated snapshot/graph metadata to discover explicit and lexical seeds, then traverse only
configured graph edges to a maximum depth of four. Scores are bounded integers with named
components. Rank by descending total score, ascending graph distance, node-kind priority
(file, module, class, function, async function, external module, repository), node ID, then path.
This makes retrieval inspectable and byte-reproducible. Phase 6 deliberately adds no embeddings,
semantic retrieval, inferred calls, LLMs, agents, or repair behavior.
