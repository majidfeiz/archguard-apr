# Local micro-pilot resource accounting

Measurements began on 2026-10-01 and final accounting completed on 2026-10-02. Docker summaries are
rounded by Docker; exact sizes are used where the registry or image inspection exposed them.

| Resource | Initial | Final | Change |
| --- | ---: | ---: | ---: |
| Host free space | 51 GiB | 49 GiB | approximately 2 GiB at `df -h` resolution |
| Benchmark root | 0 B | 13,164 KiB | 13,164 KiB |
| Docker images | 40.88 GB | 41.10 GB | approximately 0.22 GB |
| Docker containers | 183 MB | 183 MB | no retained pilot container |
| Docker volumes | 35.35 GB | 35.35 GB | 0 |
| Docker build cache | 20.70 GB | 20.70 GB | 0 |

Known exact or manifest-declared transfer is 68,528,386 bytes. This includes both Alpine layers, the
Python base layers/configs/manifests, the retained and preflight PySnooper archive transfers, two fixed
archives, and the license file. Pip additionally reported approximately 1,421 kB across pytest and its
dependencies, `python_toolbox`, and `six`. Registry-manifest response bodies were not metered, so the
observed total is reported as a lower bound rather than fabricated precision. Total estimated transfer
remained below 75 MiB, far below 5 GiB.

The largest single declared download was the 60,692,421-byte Python image layer set. No operation
approached the 1 GiB approval threshold. Final benchmark storage is below 13 MiB, far below 18 GiB,
and 49 GiB remained free, above the 7 GiB floor. The host-level decrease is larger than Docker's
rounded image delta because Docker Desktop's VM/storage allocation is not represented as a simple sum
of logical image sizes.

Retained ArchGuard-created resources are the 201 MB labeled evaluator image, its 181,499,490-byte
Python base, and the two Alpine smoke images (8,822,697 and 7,807,582 bytes). All task/build/run
containers were removed. No volume or builder was created. These exact resources may be removed later
only with explicit user approval; unrelated Docker resources must not be touched.
