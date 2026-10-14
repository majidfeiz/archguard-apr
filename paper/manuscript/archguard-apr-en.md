# ArchGuard-APR: Architecture-Constraint-Aware Multi-Agent Program Repair Using Repository Graphs and Execution Feedback

**Majid Feiz**<br>
Affiliation: `HUMAN_CONFIRMATION_REQUIRED`<br>
Email: `HUMAN_CONFIRMATION_REQUIRED` · ORCID: `HUMAN_CONFIRMATION_REQUIRED`

## Abstract

Repository-level automated program repair must reason about more than a localized failing statement.
A candidate change can satisfy a narrow test while violating dependency boundaries, modifying an
unsafe path, or relying on context that omits relevant repository structure. ArchGuard-APR is an
architecture-aware repair prototype that integrates deterministic repository analysis, immutable
repository graphs, explicit architecture profiles, graph-guided context retrieval, role-based repair
orchestration, patch-policy enforcement, isolated execution feedback, provider cost controls, and
canonical source-free evidence. We evaluate the implemented pipeline through an exploratory paired
feasibility study, not a confirmatory effectiveness experiment. Six executions were planned; four
completed and two black-4 conditions ended as pre-provider infrastructure attrition. Across two valid
paired tasks, baseline and ArchGuard conditions each achieved 0/2 successful repairs, and all four
completed outputs were classified as invalid patches. The completed executions consumed 35,431 input
tokens and 2,737 output tokens (38,168 total) at USD 0.1296325. No effectiveness advantage was
observed, and the sample provides no useful inferential basis. The study instead establishes the
engineering feasibility of composing architecture constraints with a reproducible repair pipeline and
documents patch validity and infrastructure robustness as the principal targets for future work.

**Keywords—** automated program repair; software architecture; repository graphs; language-model
agents; execution feedback; reproducibility; negative results.

## 1. Introduction

Automated program repair (APR) seeks to generate modifications that correct faulty software. Modern
repository-level tasks broaden the problem beyond a single function: tools must locate relevant code,
respect project organization, generate an admissible patch, and validate behavior in a controlled
environment. Language-model agents add flexible planning and tool use, but flexibility also increases
the number of boundaries at which a run can become invalid. A plausible textual response is not
necessarily a parseable patch; a patch that applies is not necessarily safe; a test-passing patch is
not necessarily consistent with architectural constraints.

ArchGuard-APR treats these boundaries as explicit research objects. Its pipeline separates a
vendor-neutral domain and application core from infrastructure adapters. Repository source is first
converted into a validated snapshot. Graph construction consumes the snapshot rather than rereading
the repository. Architecture evaluation consumes only a validated graph and an explicit, versioned
profile. Context retrieval operates over bounded artifacts. Patch inspection and execution are gated
by policy, isolation, budgets, and deterministic artifact persistence. This design favors auditability
and fail-closed behavior over maximizing apparent repair yield.

The paper makes two different kinds of contribution. The engineering contribution is an implemented
prototype integrating repository analysis, graphs, architecture constraints, retrieval, repair roles,
patch validation, execution feedback, provider abstraction, and canonical artifacts. The scientific
evidence is deliberately narrower: an exploratory evaluation demonstrates operational integration,
records four invalid-patch outcomes, and exposes two infrastructure attritions. Engineering size,
test count, and coverage are not treated as evidence of repair effectiveness.

The evaluation is negative and inconclusive with respect to effectiveness. It contains only two valid
paired tasks, both from PySnooper. Neither condition produced a successful repair. Therefore, the
manuscript neither claims an improvement nor performs meaningful significance testing. Its value lies
in a traceable system account, a reproducible evidence package, and a candid analysis of where an
architecture-constrained repair pipeline failed.

## 2. Background and Motivation

Generate-and-validate APR typically searches or synthesizes candidates and evaluates them against an
available correctness signal. Repository-level settings complicate every stage. Fault-relevant context
may cross module boundaries; build and test environments can fail independently of a candidate; and
test suites provide incomplete specifications. Architecture introduces another correctness dimension:
dependencies and ownership boundaries encode maintainability intent that behavioral tests may not
observe.

Architecture conformance should not be confused with automatic architecture inference. ArchGuard-APR
uses human-reviewed profiles containing explicit module assignments and rules. This choice limits
automation but makes the evaluated constraints reviewable. A violation is meaningful only relative to
that profile. The system consequently reports unassigned or ambiguous modules and fails closed rather
than silently treating an incomplete mapping as valid.

Repository graphs provide a stable intermediate representation for structural queries and context
selection. The graph is built from a validated snapshot and contains modules, definitions, imports,
and containment relationships. This representation supports deterministic traversal and avoids an
uncontrolled source reread during downstream evaluation. It is primarily static and cannot capture all
runtime behavior, reflection, generated code, or environment-dependent coupling.

Execution feedback is also necessary but insufficient. Tests can reject candidates and expose
regressions, yet sandbox startup, dependency acquisition, checkout, and evaluator configuration may
fail before scientific execution. A rigorous experiment must separate such infrastructure attrition
from repair outcomes. Phase 13 applies that distinction to black-4: its two planned conditions did not
reach the provider and are not counted as model failures.

## 3. Related Work

The verified bibliography is intentionally compact. RepairAgent presents an autonomous LLM-based
program-repair agent that selects and invokes repair tools [1]. AutoCodeRover combines language-model
reasoning with structured repository search and program representations for issue resolution [2].
SpecRover extends this direction with iterative intent extraction and a reviewer role [3]. These works
support the relevance of tool-using agents, repository context, and review feedback. They do not by
themselves establish the effectiveness of ArchGuard-APR.

Many foundational APR, benchmark, graph, retrieval, architecture-conformance, and reproducibility
records remain search leads in the Phase 14 literature matrix. Because their complete authoritative
metadata was not independently confirmed in this phase, they are not cited. This conservative policy
prevents a recognizable title or secondary search result from being converted into unsupported
bibliographic evidence. Accordingly, this paper makes no “first system” claim. Its positioning is an
integrated architecture-aware prototype and an experience report with negative exploratory results.

## 4. Research Questions

**RQ1.** Can architecture constraints, repository graphs, context retrieval, and execution feedback be
integrated into a deterministic and reproducible APR pipeline?

**RQ2.** What operational and infrastructure limitations emerge when applying the prototype to
qualified real defects?

**RQ3.** What repair outcomes, token consumption, and provider costs are observed in the exploratory
paired evaluation?

The questions separate integration feasibility from repair effectiveness. None asserts superiority.
Their operational definitions and evidence sources are summarized in
[Table 2](../tables/table-2-research-questions.md).

## 5. ArchGuard-APR Design

Figure 1 summarizes the implemented architecture, and
[Table 1](../tables/table-1-system-components.md) maps the major components to their roles and
evidence.

![Figure 1. ArchGuard-APR system architecture; components are implementation boundaries, not effectiveness claims.](../figures/system-architecture.mmd)

Entrypoints translate CLI or API requests into application services. Application services coordinate
domain objects and ports while remaining independent of provider SDKs. Infrastructure adapters handle
filesystem artifacts, Git worktrees, container execution, and model providers. This dependency
direction is continuously checked by an architecture profile.

The repair workflow uses explicit roles and state transitions rather than an unrestricted conversation
among agents. Deterministic fake transports test orchestration without making model calls. The live
provider remains behind a port, and scientific execution requires explicit acknowledgements, frozen
configuration, and cost gates. Thus “multi-agent” describes implemented role separation and
coordination; it does not imply that the exploratory study validated autonomous collaboration.

## 6. Repository Analysis and Graph Construction

Repository analysis parses Python files without importing or executing target code. It records stable
identities, module and definition summaries, imports, diagnostics, and a repository fingerprint.
Analysis output is persisted canonically. Failed or skipped files are explicit rather than silently
discarded.

Graph construction accepts only a validated snapshot. Nodes describe repositories, files, modules,
classes, and functions; edges capture containment, definitions, and import relationships. Resolution
distinguishes internal, external, ambiguous, and unresolved imports. Graph construction never rereads
target source, which makes the graph a reproducible derivative of the snapshot rather than a moving
view of a worktree.

The representation is intentionally bounded. It is not a complete semantic program graph and does not
model arbitrary dynamic behavior. Its purpose is stable structural querying, architecture evaluation,
and retrieval support.

## 7. Architecture Constraint Model

Architecture profiles are explicit YAML documents with versioned schemas. Selectors assign modules to
components; rules constrain permitted dependencies, cycles, and selected external frameworks.
Compilation separates YAML loading from domain validation. Evaluation operates on validated graphs and
emits a source-free report with profile and graph fingerprints.

Unassigned and ambiguous modules can invalidate a report. This fail-closed behavior matters because
evaluating only a subset of modules could create false confidence. Profiles require human judgment:
component boundaries and allowed dependencies represent intended design, not facts inferred from the
repository. Consequently, the system can test conformance to a reviewed model but cannot establish
that the model is uniquely correct.

## 8. Multi-Agent Repair Workflow

The workflow coordinates analysis, retrieval, generation, validation, and evaluation roles through
typed requests and results. Figure 2 shows the main sequence.

![Figure 2. End-to-end repair workflow with fail-closed validation gates.](../figures/repair-workflow.mmd)

Provider requests occur only after configuration and budget checks. Responses are converted into patch
candidates, then subjected to parsing, path, size, and policy checks. Invalid candidates become
terminal records rather than being coerced into plausible patches. Valid candidates may proceed to an
isolated evaluator. Retries are bounded and accounted for.

This design makes failure provenance visible. Provider failures, invalid patches, evaluator outcomes,
budget stops, and infrastructure failures are distinct states. That separation is essential for the
Phase 13 result: the four completed calls yielded invalid patches, while black-4 stopped during
checkout before a call.

## 9. Context Retrieval and Execution Feedback

Context retrieval combines explicit problem information with bounded graph queries. It selects stable
module and symbol neighborhoods and emits a manifest fingerprint. Budgets prevent repository content
from expanding without bound. Architecture treatment adds reviewed constraint information without
changing the underlying task order or evaluator.

Execution feedback is produced in a restricted container configuration with resource, path, network,
and output controls. The evaluator distinguishes candidate behavior from infrastructure preparation.
Isolation reduces risk but does not eliminate it: container runtimes, dependencies, kernels, and host
configuration remain part of the trusted computing base.

## 10. Security, Isolation, and Reproducibility

The implementation rejects unsafe paths, links, oversized artifacts, unexpected archive members,
identity drift, dirty worktrees, and source/gold leakage. Provider credentials remain adapter-scoped.
Cost state tracks calls started, completed, and carrying usage so that partial runs cannot silently
double-count or lose expenditure.

Canonical JSON, stable ordering, content fingerprints, and source-free diagnostics support artifact
comparison. The final source artifact SHA-256 is
`48080661ddbff3e486d47cebc63754e29d4dd4664febbb7f8143484e4c03e99d`; the final result fingerprint
is `761d9853f6ecfb4dafdaad81de781c4d49108b8b82912aeec509e173c7d56c70`.
These identities support integrity checks, not independent replication of stochastic provider output.

## 11. Experimental Methodology

Phase 13 is an exploratory feasibility evaluation with a frozen population, ordered schedule, provider
configuration, model snapshot, prices, and budget. Three qualified tasks each had baseline and
ArchGuard conditions, producing six planned execution slots. The treatment changed the supplied
architecture context while retaining the fixed orchestration and validation policy.
[Table 3](../tables/table-3-qualified-population.md) records the frozen population, while
[Table 7](../tables/table-7-attrition.md) makes the analysis denominator explicit.

The primary repair outcome was a valid evaluated repair, but terminal classifications preserve earlier
failure points. Four PySnooper executions reached the provider. The two black-4 executions did not:
ordinal 5 encountered checkout `validation_failure` with diagnostic fingerprint
`71f60e3969313f139c493cad31ee20640fd6c2870d70411debdd5ab1956994e1`, and the paired ordinal was
closed as the same task-level infrastructure attrition. Figure 3 presents the accounting.

![Figure 3. Experimental protocol and completed/attrited accounting.](../figures/experimental-protocol.mmd)

The analysis is descriptive. Two valid pairs and zero discordant successful pairs cannot support a
useful inferential effectiveness conclusion. No significance test is reported.

## 12. Exploratory Results

Four of six planned executions completed. PySnooper-2 and PySnooper-3 formed two valid pairs from one
project. Baseline produced 0/2 successful repairs; ArchGuard produced 0/2. All four completed outputs
were classified `invalid_patch`. Therefore, the observed success difference is zero, but this should
not be interpreted as equivalence.

[Table 4](../tables/table-4-per-execution-results.md) contains the per-execution records and
[Table 5](../tables/table-5-paired-comparison.md) the paired comparison. The two black-4 rows are
infrastructure attrition and have no provider outcome, token usage, or repair classification.

![Figure 4. Exploratory execution accounting: four invalid patches and two infrastructure attritions.](../figures/execution-outcomes.svg)

Baseline calls consumed 7,821 input and 1,037 output tokens at USD 0.0351075. ArchGuard calls consumed
27,610 input and 1,700 output tokens at USD 0.094525. Combined usage was 35,431 input and 2,737 output
tokens (38,168 total), costing USD 0.1296325. Four provider calls completed, no retry occurred, reserved
cost was zero, and USD 4.3703675 remained. In this tiny sample, ArchGuard used more input tokens and
cost; no broader cost claim is justified. [Table 6](../tables/table-6-token-cost.md) provides the
condition-level accounting.

![Figure 5. Observed provider cost by condition in the exploratory sample.](../figures/cost-comparison.svg)

![Figure 6. Observed input-token usage by condition in the exploratory sample.](../figures/input-token-comparison.svg)

## 13. Failure Analysis

The stored evidence establishes that all four completed responses failed patch validity. It does not
establish one unique cause. Possible mechanisms include response formatting, incompatibility with the
accepted patch grammar, path or policy rejection, insufficient task context, model behavior, or an
integration mismatch. Because raw prompts and responses are intentionally absent from the source-free
artifact, attributing individual failures among these possibilities would be speculation.

Strict validation has a dual effect. It protects repositories from malformed or unsafe modifications
and preserves a clear experimental denominator. It can also lower apparent yield relative to systems
that repair or reinterpret malformed outputs. The appropriate conclusion is not that validation caused
the model failures, but that patch admissibility is a prerequisite the observed outputs did not meet.

Black-4 is categorically different. Its checkout validation failure occurred before provider
transmission. It reveals an infrastructure robustness problem and reduces the evaluable population,
but it supplies no evidence about baseline or ArchGuard repair ability on that task.

![Figure 7. Attrition accounting preserves the planned denominator while excluding pre-provider failures from repair outcomes.](../figures/attrition-accounting.mmd)

## 14. Discussion

RQ1 receives engineering support: the repository contains an integrated, deterministic pipeline and
canonical artifacts exercising its boundaries. This is integration feasibility, not demonstrated
repair effectiveness. RQ2 identifies patch admissibility and checkout robustness as immediate limits.
RQ3 records zero successes under both conditions and higher observed ArchGuard token use and cost in
the two valid pairs.

The negative outcome redirects future work. Before expanding evaluation scale, the project should add
source-free diagnostics capable of distinguishing patch syntax from policy categories, strengthen
offline transport tests for admissible patches, and eliminate checkout attrition without weakening
identity or leakage controls. A later study would require more tasks and projects, a prospectively
defined analysis, and sufficient successful/discordant outcomes.

## 15. Threats to Validity

**Construct validity.** Success requires a patch to pass parsing, policy, application, architecture,
and evaluator gates. This is intentionally strict but may differ from other APR definitions.

**Internal validity.** Frozen ordering and canonical artifacts reduce hidden drift, yet model behavior,
prompt construction, integration code, and environmental state may influence outcomes. The evidence
does not isolate causes of invalid patches.

**External validity.** Only two valid pairs and one represented project contribute outcomes. No
generalization to other repositories, languages, defects, models, or providers is supported.

**Conclusion validity.** There were no successes and zero discordant successful pairs. The study is
underpowered and supports no inferential or superiority conclusion.

**Infrastructure validity.** Two of six slots (33.3%) attrited at checkout. Separating those slots
prevents outcome contamination but leaves the intended black-4 comparison unobserved.

**Model/provider dependence.** Results depend on `gpt-5.4-2026-03-05`, the frozen configuration,
prices, and execution date. Future configurations may behave differently.

**Task selection.** Qualification was outcome-blind, but the small population and valid-result loss
limit representativeness. **Patch policy** may reject outputs that another pipeline normalizes.

**Repository representation.** Analysis is primarily static and may miss runtime or reflective
relationships. **Architecture profiles** encode human judgment and may be incomplete or contestable.

**Security.** Sandboxing and fail-closed boundaries reduce exposure but cannot eliminate risks from
the runtime, dependencies, host, or malicious inputs. **Reproducibility** preserves inputs, aggregates,
and source-free evidence, but cannot guarantee byte-identical stochastic provider responses.
The consolidated assessment appears in [Table 8](../tables/table-8-threats.md).

## 16. Ethical and Reproducibility Considerations

No benchmark source, gold patch, credential, prompt, or provider response is included in the paper
package. Negative results and attrition are retained. Costs and calls are reported rather than hidden.
The manuscript uses only verified citations and marks unresolved human decisions. Final interpretation,
authorship, disclosure, and intellectual responsibility remain with the human author.
[Table 9](../tables/table-9-reproducibility.md) indexes the source-free reproducibility
package and its integrity checks.

## 17. Conclusion and Future Work

ArchGuard-APR integrates architecture constraints, repository graphs, context retrieval, role-based
repair orchestration, patch validation, isolated feedback, and canonical evidence. Phase 13 confirms
that these elements can be assembled into auditable research infrastructure, while providing no
evidence of repair advantage: both conditions achieved 0/2, all completed outputs were invalid, and
two slots attrited before provider use. Future work should prioritize valid-patch production,
diagnostic resolution, checkout robustness, and a larger prospectively powered evaluation.

## Data Availability

Canonical source-free data are available under `research/results/phase-13/` and transformed publication
data under `paper/data/`. No target source or gold patch is distributed in this package.

## Artifact Availability

The repository provides claim traceability, deterministic build scripts, tables, figures, fingerprints,
and verification tests. The target venue remains undecided; the article is not submitted or accepted.

## Author Contributions

`HUMAN_CONFIRMATION_REQUIRED`

## Funding

`HUMAN_CONFIRMATION_REQUIRED`

## Conflict of Interest

`HUMAN_CONFIRMATION_REQUIRED`

## References

[1] I. Bouzenia, P. Devanbu, and M. Pradel, “RepairAgent: An Autonomous, LLM-Based Agent for Program Repair,” arXiv:2403.17134, 2024.

[2] Y. Zhang, H. Ruan, Z. Fan, and A. Roychoudhury, “AutoCodeRover: Autonomous Program Improvement,” arXiv:2404.05427, 2024.

[3] H. Ruan, Y. Zhang, and A. Roychoudhury, “SpecRover: Code Intent Extraction via LLMs,” arXiv:2408.02232, 2024.

## Appendix A. Reproducibility Fingerprints

Final manifest: `8afb87add96e29898ae712f8ef08928b9ba1290a0aabc3ce34bac82adb4b86c2`.
Import: `80eac046fc614cad1beb7de127ba69aa907b5c588d5409c30e92e5b685c0dc28`.
