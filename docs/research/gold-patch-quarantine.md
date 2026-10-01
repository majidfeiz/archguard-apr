# Gold-patch quarantine

The trust boundary has three physically separate zones: agent-visible workspace, evaluator-only tests,
and quarantined gold. BugsInPy fixed revisions and patches and SWE-bench `patch` are quarantined.
`test_patch`, `FAIL_TO_PASS`, and `PASS_TO_PASS` are evaluator-controlled. Oracle retrieval is never
primary agent input. Only hashes may cross the boundary.

Before each run, scanners reject prohibited field names and registered canaries in prompts, context,
feedback, logs and output artifacts. Fixed revisions cannot be graphed or retrieved. Evaluation occurs
through a port separate from repair agents and returns source-free evidence. Evaluator and quarantine
mounts must be read-inaccessible to the candidate workspace; access is auditable and fail-closed.
