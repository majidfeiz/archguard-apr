# Phase 12.8F.4 reviewed evaluator adapters

Baseline: `f666f2e95e5f93fefc10c5353335cd24de80b54d`, version `0.12.8`.

Pinned BugsInPy metadata at `11c5f1eea954a42132cfd06bf257766a7963e0fd` proves that every Batch A
target test is present at the fixed revision but absent as a file or selected symbol at the buggy
revision. The reviewed evaluator therefore uses the fixed-revision test blob as quarantined,
read-only evaluator material for both executions. Only its SHA-256 and provenance are retained.

The official commands remain unchanged. PySnooper uses its declared pytest command; black also uses
the official generated empty `tests/__init__.py` marker; cookiecutter uses its official tox command
with a writable temporary tox work directory and offline pip policy. Buggy and fixed executions mount
byte-identical evaluator material, while target source remains independently verified and read-only.
Evaluator fixture paths are explicit metadata and are never derived from framework-specific selectors;
in particular, black's dotted unittest selector maps to `tests/test_black.py`.

Run `37748121571` proved source separation but produced zero valid qualifications. It is not imported.
Batch B and Phase 13 are not run, and `phase_13_ready=false`.

| Task | Old adapter | Reviewed v3 adapter |
|---|---|---|
| PySnooper-1 | `1ad10c19e8fda53180666da7ef1fb1723652cc61b71c15b7efd6f37e19f3e7af` | `d3a4938e74e6287056a21ab937a167e18c3c8c0e274a719f713068f28e96db10` |
| PySnooper-3 | `41c254922a6bbb4dad7eb078a44708cdb55805d329f9805edc3ad356f5003662` | `8be2d7c2752d4a31b101571f85e65416c64243dbaaa46782d5b1efaa3b7fc244` |
| black-1 | `7d08b9f8f51ff4984fb67a5c5510532dd608a985aa9f29ea33c0a799f93352e8` | `45af5d136425d7378e1a66f5c7deb6cb162442863a353fcb5b795bcef9960162` |
| cookiecutter-4 | `9979bdc6351f42b3dac14c3ebb9ff06a70bc59864fbd293df526149ed819a06f` | `cd1ad0be37d784697a74099fe350a92f6f2f6887eb4553afecb3f200ecf546cf` |

Changed fields are schema, revision-specific selector plans, evaluator source/provenance, installation
plan, working directory, framework, quarantine policy, review status and fixture identity. Revisions
and official selectors/commands do not change. Historical artifacts remain bound to the old values.
The superseded black v3 fingerprint
`aefafeab61e267da995bfa3e57c817316b85a1fbb80b59b3cfc8b2125d2554e0` derived its fixture path
incorrectly from the dotted unittest selector and remains historical, non-qualification evidence.
