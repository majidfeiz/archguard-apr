# Controlled baselines

C0 SinglePass-Flat uses the matched provider/model, task and input/output limits, deterministic lexical
context, one proposal and one round. It receives no graph, architecture, execution or peer feedback;
the trusted evaluator still measures final functional and architecture outcomes. C1 enables graph
retrieval, architecture awareness, multiple agents/candidates, sandbox feedback, refinement and
evidence ranking. Fixed-budget and natural-system views must be reported separately. The lexical
baseline lowercases issue terms, counts occurrences in path plus content, sorts by descending integer
score then path, and admits whole documents within the byte budget. It is not equivalent to graph
retrieval and uses no oracle, fixed revision or gold information.
