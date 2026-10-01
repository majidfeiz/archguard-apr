# Linux/x86 execution requirements

Observed host: Darwin ARM64 (`arm64`), so metadata and offline fixtures are valid but final Linux/x86
readiness is not. The official SWE-bench framework recommends x86_64, at least 120 GB free storage,
16 GB RAM and 8 CPU cores; ARM support is described as experimental. Use Linux x86_64, pinned Docker
image digests, fixed CPU/memory/PID/timeouts, isolated network policy and sufficient additional space
for selected BugsInPy environments. Re-measure actual images/tasks before freezing capacity. ARM or
emulated timings must be labelled infrastructure smoke observations, never final performance results.
