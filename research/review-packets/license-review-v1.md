# Phase 12.8E license review packet

This factual audit is not legal advice. PySnooper and Black have verified MIT license files;
Cookiecutter has a verified BSD-3-Clause license file. The SWE-bench framework has a verified MIT
license file. The BugsInPy frozen tree has no license file and remains unresolved. SWE-bench Verified
dataset redistribution remains unresolved and its payload is excluded. Framework, dataset, and target
project conclusions are deliberately independent.

## BugsInPy maintainer-contact packet (not sent)

- Repository/revision: `https://github.com/soarsmu/BugsInPy` at
  `11c5f1eea954a42132cfd06bf257766a7963e0fd`.
- Finding: no license file in the immutable tree; public visibility and README text were not treated as
  permission.
- Requested clarification: identify the governing license for framework code and benchmark metadata,
  and explicitly clarify research use, execution, metadata redistribution, and patch redistribution.
- ArchGuard policy meanwhile: external locator only; no copied framework code or task files.

Canonical evidence: `research/licenses/license-registry-v1.json`.
