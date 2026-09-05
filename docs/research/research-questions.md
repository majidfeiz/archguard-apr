# Planned research questions

No hypothesis has been tested.

## RQ1: Does explicit architecture-constraint validation increase the rate of functionally correct and architecture-compliant repository-level patches?

- Hypothesis: Validation increases joint acceptance.
- Null hypothesis: No difference between compared conditions.
- Independent variables: Validation on/off.
- Dependent variables: Joint acceptance and correctness.
- Intended metrics: Joint acceptance rate and new violation rate.
- Preliminary analysis: Paired comparisons and repository-cluster bootstrap intervals.

## RQ2: Does repository-graph retrieval improve fault localization and relevant-context selection compared with semantic retrieval alone?

- Hypothesis: Graph retrieval improves rank and recall.
- Null hypothesis: No difference between compared conditions.
- Independent variables: Graph versus semantic retrieval with matched context budget.
- Dependent variables: Localization and context relevance.
- Intended metrics: MRR, precision and recall against independent labels.
- Preliminary analysis: Paired differences with cluster bootstrap intervals.

## RQ3: Does multi-agent critique reduce newly introduced architecture violations and regressions compared with a single-agent repair pipeline?

- Hypothesis: Critique reduces violations and regressions.
- Null hypothesis: No difference between compared conditions.
- Independent variables: Critique on/off with equal total budget.
- Dependent variables: New violations and regressions.
- Intended metrics: Violation counts/severity and regression rate.
- Preliminary analysis: Paired categorical contrasts and repository-grouped count distributions.

## RQ4: What latency, token, and monetary overhead does architecture-aware multi-agent repair introduce?

- Hypothesis: Additional components increase resource use.
- Null hypothesis: No difference between compared conditions.
- Independent variables: Pipeline variant with matched task/model.
- Dependent variables: Latency, token use and cost.
- Intended metrics: Median/tail latency, input/output tokens, cost per task and accepted patch.
- Preliminary analysis: Paired bootstrap intervals and timestamped pricing; explicitly report missing usage.

## RQ5: Which ArchGuard-APR components contribute most strongly to repair effectiveness?

- Hypothesis: Removing a component reduces joint acceptance.
- Null hypothesis: No difference between compared conditions.
- Independent variables: Prespecified component ablations.
- Dependent variables: Joint acceptance and overhead.
- Intended metrics: Acceptance-rate difference and cost per accepted patch.
- Preliminary analysis: Paired contrasts with Holm correction; unregistered interactions exploratory.
