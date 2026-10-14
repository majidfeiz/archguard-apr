# English manuscript outline

## Title
ArchGuard-APR: Architecture-Constraint-Aware Multi-Agent Program Repair Using Repository Graphs and Execution Feedback

## Abstract structure
Context; architecture-aware prototype; deterministic method; exploratory six-slot protocol with four
completed outcomes and two infrastructure attritions; zero successful repairs; implications and limits.

## Keywords
Automated program repair; software architecture; repository graphs; LLM agents; reproducibility.

## 1. Introduction
Motivation, precise gap, implemented scope, contributions, and explicit negative-result framing.

## 2. Background and Motivation
APR, repository-level reasoning, architecture conformance, execution feedback, and reproducibility.

## 3. Related Work
Use only independently verified primary records. Human synthesis and novelty approval required.

## 4. Research Questions
- **RQ1:** Can architecture constraints, repository graphs, and execution feedback be integrated into a deterministic and reproducible APR pipeline?
- **RQ2:** What operational and infrastructure limitations emerge when applying the prototype to qualified real defects?
- **RQ3:** What are the observed repair outcomes, token usage, and provider costs in the exploratory paired evaluation?

## 5. ArchGuard-APR Architecture
Entrypoints, vendor-neutral domain/application layers, snapshots, graphs, profiles, validation,
orchestration, provider ports, execution sandbox, and canonical artifacts.

## 6. Methodology
Qualified population, frozen protocol, paired conditions, safety boundaries, outcome definitions,
cost accounting, attrition policy, and descriptive-only analysis.

## 7. Exploratory Evaluation
Six planned slots; four completed executions; two pre-provider black-4 attritions; one represented
project among valid pairs. Do not describe this as confirmatory.

## 8. Results
Two valid pairs; baseline 0/2 and ArchGuard 0/2; four invalid patches; no observed effectiveness
difference. Report 35,431 input tokens, 2,737 output tokens, and USD 0.1296325 total cost.

## 9. Failure Analysis
The evidence establishes patch-format/policy rejection but does not isolate whether model behavior,
formatting, validation policy, or task constraints caused each invalid patch. Unknown causes remain
unknown; black-4 is infrastructure attrition rather than model or repair failure.

## 10. Threats to Validity
Two valid pairs, one project, 33.3% attrition, no successes, rejection-dominated outcomes, no power.

## 11. Discussion
Primary positioning: architecture-aware APR system design with exploratory feasibility evaluation.
Secondary positioning: experience/negative-results report. Human interpretation required.

## 12. Reproducibility and Ethics
Canonical source-free artifacts, fingerprints, budgets, security boundaries, human responsibility.

## 13. Conclusion
Pipeline integration is demonstrated as engineering infrastructure; effectiveness remains unresolved.

## Data Availability
Source-free tables are in `paper/data/`; target source and model responses are not published here.

## Artifact Availability
Code, deterministic builders, claim matrix, tables, figures, and fingerprints accompany the paper.

## Author Contributions
`HUMAN_APPROVAL_REQUIRED`: specify conceptualization, implementation, analysis, and writing roles.

## Conflict of Interest
`HUMAN_APPROVAL_REQUIRED`: provide the authors' disclosure.
