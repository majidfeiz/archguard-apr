# Candidate pool v1

`archguard.candidate-pool/v1` contains source-free task identity and pre-repair eligibility metadata:
immutable index, buggy and trusted-fixed revisions; official repository; evaluator locator; language
and Python version; measured archive-size bound; execution ceilings; secrets/network/gitlink/LFS
flags; project-license binding; eligibility and a reason code. It must not contain patches, source,
repair outcomes, conformance outcomes, or scores.

The registry binds the license registry, selection policy, canonical observed-input fingerprint and
its own fingerprint. `final_pilot_list_frozen` and `phase_13_ready` remain false in Phase 12.8E.
