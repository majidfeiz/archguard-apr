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

Phase 12.8F separates metadata, buggy source, fixed controls, build context, transient logs, and
source-free evidence. Hooks, submodules and LFS smudging are disabled; gitlinks, escaping symlinks and
LFS pointers fail closed. Dependency networking is confined to container builds; evaluator containers
have no network, credentials, Docker socket, writable root, capabilities, or host worktree mount.
Output is bounded before hashing and raw logs are discarded. Exact allowlists, hostile-ZIP checks,
append-only prior evidence, conflict review, serial batching, transfer/disk ceilings, and label-scoped
cleanup limit leakage, resource exhaustion, result substitution, and unrelated Docker deletion.
Phase 12.8F.1 removes reliance on runner-installed `rg`: a repository-controlled standard-library
scanner fails on absence, decoding errors, secrets, diff/source/gold/raw-log markers and runner paths.
Exact base images are explicitly pulled for linux/amd64, identity-recorded and acquired-image cleanup is
ownership-aware. Structured allowlisted argv prevents shell-command ambiguity; diagnostics retain only
bounded normalized hashes and categorical stages/codes.
Phase 12.8F.2 separately binds fixed-control revision, stage, selector, dependency environment and image
identity. Collection, execution and infrastructure failures cannot masquerade as defect outcomes;
fixed failures remain review-required and raw diagnostic output remains temporary and unpublishable.
Phase 12.8F.3 makes target-source absence from the dependency image explicit and verifies each mounted
tree inside the network-disabled container. Independent revision, Git-tree, working-tree, build-context
and container-visible fingerprints fail closed on stale cache, wrong checkout, wrong mount or working
directory. Fixed `EXIT_ZERO` semantics are separate from buggy `TEST_FAILURE` semantics.
Phase 12.8F.4 quarantines fixed-revision evaluator tests outside target trees and mounts the same
hash-bound file read-only for both revisions. Agents, prompts and retained artifacts cannot access test
contents. Offline tox policy rejects dependency download attempts; only reviewed generated empty setup
markers may shadow target paths.
Phase 12.8F.4.1 prevents nested evaluator mounts below the read-only source mount. Framework-specific
selectors resolve only to `/evaluator`; host and container fixture hashes must agree before collection.
Project imports, evaluator imports and tox bootstrap fail as non-scientific preflight categories.
Temporary package markers and tox configuration remain outside target trees and are removed with all
owned runtime resources.
Phase 12.8F.4.2 requires operation-backed, ordered runtime transitions. Exact non-overlapping mount
destinations, mount read-only state, writable isolated temporary paths, absent Docker socket, disabled
execution network and container-visible fixture identity are checked before import or collection.
Only fingerprints and allowlisted outcomes are retained; evaluator bytes and raw diagnostics remain
excluded.
Phase 12.8F.4.2.1 mounts `/tmp` as bounded `noexec,nosuid,nodev` tmpfs with explicit non-root-compatible
ownership and mode. HOME, temporary data, bytecode, and pytest cache are isolated below that mount.
Behavioral probes reject missing, symlinked, protected-overlapping, non-tmpfs, ownership-incompatible,
uncleaned, or unwritable paths without retaining their container paths.
Phase 12.8F.4.2.2 resolves reviewed logical pytest selectors exclusively below `/evaluator`, rejects
absolute/traversing or mismatched fixture paths, and requires exactly one collected approved node.
Collection—not dotted-package or `runpy` execution—proves standalone pytest evaluator loading. Only
selector, mount-root, collected-node, and immutable fixture fingerprints enter retained evidence.
