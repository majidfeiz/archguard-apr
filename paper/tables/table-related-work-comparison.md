# Table 10. Verified related-work feature comparison

`NR` means not reported or not established from the inspected primary source; it is not evidence of absence.

| Approach | Repository context | Architecture constraints | Graph context | Execution feedback | Agentic | Sandbox/isolation | Reported scale | Artifact availability |
|---|---|---|---|---|---|---|---|---|
| GenProg | no | no | no | tests | no | NR | 16 programs | code and data reported |
| SemFix | no | no | no | tests | no | NR | SIR and Coreutils subjects | NR |
| Angelix | no | no | no | tests | no | NR | real C systems | implementation reported |
| Prophet | no | no | no | tests | no | NR | 69 defects | project artifacts reported |
| Elixir | limited | no | no | tests | no | NR | Defects4J and Bugs.jar | NR |
| CoCoNuT | local context | no | no | tests | no | NR | multiple repair corpora | implementation reported |
| RepairAgent | yes | no | NR | yes | yes | NR | Defects4J | code reported |
| AutoCodeRover | yes | no | structured program search | yes | yes | NR | 300 SWE-bench-lite issues | code reported |
| SpecRover | yes | no | structured repository context | yes | yes | NR | 2,294 SWE-bench issues | code reported |
| ArchGuard-APR | yes | explicit profiles | canonical repository graph | isolated tests | role-based | yes | 6 planned; 4 completed | this repository |

Source keys and verification evidence are recorded in `paper/references/literature-matrix.csv`.
