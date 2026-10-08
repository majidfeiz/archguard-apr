# Incident: Run 37672954475 fixed-control failures

Phase 12.8F.1 Batch A ran on native Linux x86_64. All four tasks reached three infrastructure-valid
buggy repetitions with stable failure signatures. PySnooper-1, PySnooper-3, black-1 and cookiecutter-4
then recorded `fixed_control_passed=false`; zero tasks qualified.

The Artifact SHA-256 is `f96ca46c1af3a2d6b48aaf278edc610c4db7f1f1019f4bd357b2f22db0dc6dbd`
and manifest fingerprint is `cba04d1c7165f6ad66995a370b9ec972a6ec7ee6a4dbf2b6d1ce77a6b80c6ef9`.
It contains no fixed stage, exit code, counts, normalized class or signature, so it cannot prove whether
the failures arose from revision acquisition, installation, collection, execution, sandbox compatibility
or result parsing. No task-specific root cause is claimed, no adapter is amended, and the Artifact is
preserved but not imported as qualification evidence.

Phase 12.8F.2 adds the missing source-free diagnostic fields and prevents a failed control from becoming
an inferred scientific classification. A new Batch A run and human review remain required.

Follow-up run `37684840237` reached fixed execution for every task but exposed inherited buggy outcome
semantics. Its separate incident record documents the Phase 12.8F.3 resolution. Both runs remain
non-imported and qualify no task.
