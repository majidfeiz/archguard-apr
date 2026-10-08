# Incident 37843274763: disconnected v3 runtime plans

Run `37843274763` produced a valid source-free artifact and zero qualifications. PySnooper-1 stopped
with Docker exit 125 before scientific execution because the evaluator file target did not exist
inside the read-only `/workspace` source bind and the runner attempted a nested bind there.
PySnooper-3 referenced `/workspace/tests` instead of its quarantined file. Black's generated package
marker and import plan were declared but not executed. Cookiecutter's offline-tox token did not select
or bootstrap an offline environment.

The run remains historical and non-imported. No raw log, target source, test source, patch or gold
material is retained. Phase 12.8F.4.1 adds a non-overlapping `/evaluator` mount, runtime selector
construction, explicit preflight categories and per-task source-free execution-plan evidence. This is
an engineering correction, not a scientific result or task substitution.
