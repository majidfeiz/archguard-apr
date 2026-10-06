# Phase 12.8D verification

Baseline was clean local `main` at `d79c5b007fd942f80fd4d76decb56e39a3577b74`, version `0.12.8`.

Two valid ZIP identities have different roles:

- GitHub artifact download container: run `37433179494`, head
  `d79c5b007fd942f80fd4d76decb56e39a3577b74`, SHA-256
  `f99257ebd74d66d5a53242023a30d2f9026590aa42a0e7838c367d69ec07a58b`. This is provenance only.
- Canonical package produced by `phase128c package`: SHA-256
  `c737bd847704660eeb13de1a925c65283e98ce3d7fb22ce34cf4dc29b60dbce9`. This was validated and
  imported; the two container serializations are not expected to be byte-identical.

The canonical archive has the exact nine-file allowlist and valid checksums/canonical records. Its
manifest fingerprint is `70305948c61e2dcb662f40ca6c5906f9934c97bcff6c79746ff061186948e5fb`,
graph fingerprint `261aa8835ff52a407e13d1e9d8f9bbfd06c379b1003121c5633cdcbcf58394ad`,
canonical graph `b1c318faba70d50225ceba74254edb18727013291de8607695334f8f0a98802c`,
constraint evaluation `52e1a62506f0c616efa6c3737c073bfa017d94739ac6a1e430e899f761d48075`,
and determinism `a1cae0b8ea43ff162897c4d36e7755fbb0f3fb5341bcef1163d059cf5136a540`.
The two independent evidence hashes are both
`f360d53b815e5960cd516cec5f7dd3d71348d4649f946194bd326d9bbe6958de`.

Three independent temporary imports were byte-identical with file SHA-256
`4f24a8c72e15e0461af34ae167f4d98437da5fc824cc6132aab6001b3ffcce58` and imported evidence
fingerprint `2eb422f3a48222aca7f664537f0fad41441a1841886b3a61280af00e50a9639c`.
Identical reimport did not mutate output; contradictory overwrite was rejected.

The user-authorized human decision is `APPROVE`, bound to every evidence identity above. The exact
prior AMEND record is retained and hash-linked. Frozen profile fingerprint
`950cd9889d5d4335e60b7429d2feddf2230db42654e5ec844edd813596b6d6d7` recompiles identically and
fails closed on drift. The protocol decision is unchanged.

PySnooper-specific `ARCHITECTURE_ANALYSIS_INCOMPLETE` and `PROFILE_REVIEW_REQUIRED` are resolved.
Their global facts remain false because future selected projects are incomplete. Population,
diversity, candidate-pool, pilot-selection, task-freeze, licensing, protocol-review, and provider
blockers remain. Explicitly, `phase_13_ready=false`.

Verification completed with 694 passing tests and 3 Docker-dependent skips under both Python 3.12
and Python 3.13. Combined statement/branch coverage is 90.12%. Ruff format/lint, strict mypy,
pre-commit, frozen lock validation/synchronization, sdist/wheel build, workflow YAML parsing, and
self-architecture validation passed. `actionlint` and `shellcheck` were not installed locally.
