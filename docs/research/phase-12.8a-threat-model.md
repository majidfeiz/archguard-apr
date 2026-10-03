# Phase 12.8A threat model

Threats include license-scope confusion, mutable revisions, source/gold leakage, outcome-driven task
selection, malicious archive paths, execution of target code on the host, Docker privilege escape,
resource exhaustion, stale profile decisions, and pilot-to-confirmatory overclaiming. Controls are exact
revision/hash binding, separate scope records, source-free canonical artifacts, outcome-blind sorting,
external-only static analysis, non-root/network-disabled/read-only Docker plans, hard resource ceilings,
fingerprint-bound reviews, fail-closed cleanup, and distinct pilot/final readiness gates.
