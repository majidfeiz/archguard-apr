# Phase 12.8F.4.2.1 writable runtime mounts

Baseline: `8e8610810e6ddefec19adccea6bf7828fdeb86d0`, version `0.12.8`.

Run `37850406131` reached `INSTALLATION_PREPARED` and then stopped at
`MOUNT_PROBE_TEMPORARY_WRITABLE`. It produced zero buggy scientific attempts, did not attempt the
fixed control, qualified no task, and remains historical non-imported evidence.

The failed runtime used separate tmpfs mounts for `/tmp/archguard` and `/tmp/home` without explicit
UID, GID, or mode. Those mounts replaced the image-prepared directories, and the actual bounded
create/write/delete probe failed as non-root UID/GID `65532:65532`. The repair mounts one bounded
`/tmp` tmpfs with `rw,noexec,nosuid,nodev,mode=1777,uid=65532,gid=65532`, then creates
`/tmp/home`, `/tmp/archguard`, and `/tmp/pytest-cache` as the runtime user after the mount exists.

Runtime configuration uses `HOME=/tmp/home`, `TMPDIR=/tmp/archguard`,
`PYTHONDONTWRITEBYTECODE=1`, `PYTHONPYCACHEPREFIX=/tmp/archguard/pycache`, and pytest
`cache_dir=/tmp/pytest-cache`. The probe verifies actual create, bounded write, fsync, stat, close,
delete, ownership compatibility, non-symlink status, tmpfs type, cleanup, and separation from all
read-only mounts. It never executes a temporary file.

The security summary's `adapter-registry-v2.json` entry is the repository's legacy filename. Its
reviewed active canary record uses `archguard.evaluator-adapter/v3`; the filename is not a schema
claim.

Only PySnooper-1 is enabled. Batch A, Batch B, and Phase 13 remain prohibited, and
`phase_13_ready=false`. The expected artifact remains
`archguard-phase-12-8f4-2-1-pysnooper-1-runtime-canary-<run-id>`.

A completed reviewed-v3 canary is marked `PRIOR_EVALUATOR_NOT_COMPARABLE`: the earlier PySnooper-1
classification used a different evaluator/runtime contract and is not silently treated as matching or
conflicting evidence. Qualification still requires all runtime transitions, three stable intended
buggy failures, and the passing fixed control.
