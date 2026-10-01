# One-factor ablations

C2 hides architecture information and refinement/ranking signals; trusted final measurement remains.
C3 disables graph retrieval in favor of the frozen lexical baseline at the same context budget. C4
withholds intermediate execution outcomes while retaining trusted final execution. C5 uses one repair
agent while deterministic validators remain. C6 disables refinement after initial generation with the
same documented initial candidate budget. C1 is the reference. The fairness report enumerates every
field difference and rejects unrelated provider, model, prompt, budget, timeout, image, retry or
measurement changes. Downstream causal consequences are recorded, not disguised as extra factors.
