# External benchmark onboarding

Accessed 2026-10-01 under the authorized official-source policy. BugsInPy framework revision
`11c5f1eea954a42132cfd06bf257766a7963e0fd` was read from
`https://github.com/soarsmu/BugsInPy`; its checkout contains reference patch files, so the entire clone
was moved to `GOLD_QUARANTINED` before use. Its source-free inventory contained 17 project directories
and 501 bug records at this revision; these observed counts are metadata, not qualified tasks.

SWE-bench framework revision `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e` was read from
`https://github.com/SWE-bench/SWE-bench`. Official SWE-bench Verified dataset HEAD was
`78f471bf655a3137b2e8a75af1501690ec009ec3` at
`https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified`; the 500-task count is the framework's
official declaration. Dataset payload was not downloaded, so no `patch` or evaluator fields were
opened. No task repository was acquired, built or executed.

External storage uses absolute resolved paths outside Git with `public`, `evaluator-only`,
`gold-quarantine`, `workspaces`, `images`, `results` and `logs` zones. CLI acquisition requires explicit
network acknowledgement and rejects repository-contained/symlink roots. `.gitignore` is defense only.
