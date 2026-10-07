# Outcome-blind preparation-pool selection

The Phase 12.8E input scope was declared as PySnooper, Black, and Cookiecutter at BugsInPy revision
`11c5f1eea954a42132cfd06bf257766a7963e0fd`. Selection uses only pre-repair metadata. It filters for
complete immutable identities, verified upstream project licensing, Python/static-analysis and Linux
x86 compatibility, bounded resources, no secrets or evaluator network, and no gitlink/LFS dependency.
It then groups by project, sorts by source-free task identifier, round-robins across sorted projects,
caps each project at four, and selects 8–12 tasks. There is no random seed because selection is not
random. Later outcomes cannot replace a selected task.

The canonical algorithm and its fingerprint are in
`research/candidates/selection-policy-v1.json`. This is a preparation pool, not the final pilot list.
