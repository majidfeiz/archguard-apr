# Benchmark registry

`archguard.benchmark-registry/v1` records immutable upstream revisions, adapter versions, declared
counts, platforms, acquisition policy, citation, license, redistribution status and limitations.
`archguard.benchmark-task/v1` references source-free artifacts; it never embeds repositories, hidden
tests or gold patches. Tasks have explicit states and exclusions are retained rather than dropped.

Snapshot identity is canonical and excludes host paths, timestamps, cache locations, process/container
IDs and usernames. Task, registry, split, leakage and snapshot identities are SHA-256 fingerprints of
semantic fields. Acquisition timestamps belong only in non-semantic provenance records.
