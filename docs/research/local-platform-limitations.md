# Local platform limitations

The host is Apple Silicon (`arm64`) with Docker Desktop. Immutable Alpine 3.20.10 smoke images reported
`aarch64` for `linux/arm64` and `x86_64` for `linux/amd64`, confirming that Docker can start both
platforms. The real PySnooper qualification used native Linux ARM64 to minimize transfer and disk use.

This does not establish Linux x86_64 final-evaluation readiness. Emulated AMD64 performance is not a
valid runtime measurement, no SWE-bench task image was executed, and the Phase 13 Linux/x86 gate
remains unresolved. Final experiments still require a controlled native Linux x86_64 host.
