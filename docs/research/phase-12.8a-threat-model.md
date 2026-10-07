# Phase 12.8A threat model

Threats include license-scope confusion, mutable revisions, source/gold leakage, outcome-driven task
selection, malicious archive paths, execution of target code on the host, Docker privilege escape,
resource exhaustion, stale profile decisions, and pilot-to-confirmatory overclaiming. Controls are exact
revision/hash binding, separate scope records, source-free canonical artifacts, outcome-blind sorting,
external-only static analysis, non-root/network-disabled/read-only Docker plans, hard resource ceilings,
fingerprint-bound reviews, fail-closed cleanup, and distinct pilot/final readiness gates.

Phase 12.8B adds a 250 MiB aggregate acquisition ceiling, full immutable commit identities, exact
remote verification, disabled hooks/submodules/LFS, symlink-escape and gitlink rejection, isolated
buggy/fixed/metadata directories, duplicate/traversal-safe evidence packaging, and cleanup before
upload. Only the buggy tree enters static analysis. The fixed tree is identity-checked but never used
for profile or graph generation. License uncertainty is preserved as data rather than converted into
an engineering failure or an inferred permission.

Phase 12.8C uses two exact tooling selectors so future production modules cannot be silently captured.
It acquires only the immutable buggy revision, runs independent graph/evaluation passes, and requires
byte identity. The flat source-free allowlist is revision/profile/graph/hash bound and rejects source,
gold, logs, secrets, symlinks, traversal, and contradictory readiness. Local ARM evidence cannot
qualify the profile; native Linux x86 evidence must be imported and reviewed before approval/freeze.

Phase 12.8E adds independent framework/dataset/project license scopes, rejects SPDX inference without
an official immutable license file, and preserves unresolved dependencies. Candidate input is
source-free and outcome-blind; hidden-answer and repair-result fields fail closed. Exact revisions,
bounded archive sizes, platform metadata, gitlinks and LFS are checked before deterministic
project-stratified selection. The manual workflow executes no acquired project or evaluator, compares
two regenerations byte-for-byte, uses a strict flat evidence allowlist, and cleans on every exit path.
