# Phase 12.8F.4.1 v3 adapter runtime verification

Baseline: `085121992030164e864e2550b4278d6d012abbcd`, version `0.12.8`.

Run `37843274763` completed artifact production but qualified zero tasks. Its source-free evidence is
historical and non-imported. The run proved that reviewed v3 metadata was serialized but not fully
connected to execution: evaluator files were nested below the read-only `/workspace` bind mount,
selectors still named project-relative test paths, and installation/offline-tox tokens had no runtime
consumer.

Phase 12.8F.4.1 mounts evaluator storage independently and read-only at `/evaluator`, rewrites pytest
and tox selectors to the actual mounted fixture, exposes unittest fixtures through an evaluator-only
package path, and performs collection, project-import, fixture-identity and offline-tox preflights
before any scientific attempt. Generated `tests/__init__.py` and tox configuration live only in
runner-temporary evaluator storage. Target source remains read-only and byte-identity checked.

The canonical black-1 fingerprint is
`45af5d136425d7378e1a66f5c7deb6cb162442863a353fcb5b795bcef9960162`.
The previously reported `aefafeab61e267da995bfa3e57c817316b85a1fbb80b59b3cfc8b2125d2554e0`
bound an invalid dotted-selector-derived fixture path. Correcting that field canonically changed the
fingerprint; shortened forms are display-only and never evidence identities.

The workflow remains Batch-A-only and produces exactly one source-free artifact named
`archguard-phase-12-8f-qualification-batch-a-<run-id>`. Job success means artifact production
completed, not that any task qualified. Batch B and Phase 13 are prohibited and
`phase_13_ready=false`.
