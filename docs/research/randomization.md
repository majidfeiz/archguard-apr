# Randomization and repetitions

The schedule records one seed, preserves frozen task order, and hashes seed/task/repetition/configuration
to randomize configuration order within each task block. This interleaves systems to mitigate provider
drift and resumes without changing existing block indices. Repetition count is explicit; two is used
only by the fixture and three is a configurable pilot example, not the final study count. Repeated runs
on one task are correlated observations, never independent benchmark tasks. Live operational metadata
records date/window, returned model/tier, region when known and evaluator hardware outside identity.
