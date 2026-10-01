# Benchmark strategy

Phase 11 prepares, but does not execute, an empirical study. Tier A is BugsInPy for controlled
Python repair; Tier B is a curated pilot of SWE-bench Verified for external validity. External tasks
become eligible only after immutable acquisition, license review, reproduction, architecture analysis,
graph construction, isolated evaluation and gold-boundary checks. No external task was acquired in
Phase 11; the three controlled fixtures verify metadata shapes, not benchmark compatibility.

The planned questions ask whether architecture constraints improve joint functional/architecture
acceptance (RQ1), graph context changes effectiveness and efficiency (RQ2), iterative multi-agent
refinement improves over single-pass repair (RQ3), individual components contribute under ablation
(RQ4), and what compute/provider costs each configuration incurs (RQ5). Phase 11 answers none of them.

Mac ARM fixture results are engineering checks and are not interchangeable with final Linux/x86_64
evaluation. Acquisitions require an explicit command and an untracked cache outside the repository.
Each task environment must record architecture, OS base, Python version, system packages, dependency
lock, image/build-context digest, CPU, memory, PID and timeout limits, network policy and external
service requirements. Platform results remain separate; SWE-bench heavy evaluation is treated as
Linux/x86-oriented until a verified current harness establishes otherwise.
