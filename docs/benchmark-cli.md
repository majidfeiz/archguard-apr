# Benchmark CLI

Registry and cache operations are offline and source-free:

```bash
archguard benchmark registry validate --registry configs/benchmarks.fixture.yaml
archguard benchmark registry inspect --registry configs/benchmarks.fixture.yaml
archguard benchmark cache verify --cache /untracked/cache
archguard benchmark cache inspect --cache /untracked/cache
archguard benchmark tasks list --snapshot /path/to/snapshot.json
```

`benchmark acquire` is an explicit boundary. Phase 11 exits 4 with `network_required: true` until an
approved external adapter is configured; import, tests and normal CI never acquire data. Invalid input
exits 2 and an invalid cache exits 3. Output is canonical concise JSON and never displays source, hidden
tests or gold. The fixture demo supports `synthetic`, `bugsinpy-compatible`, and
`swe-bench-compatible`; compatibility describes metadata shape only.
