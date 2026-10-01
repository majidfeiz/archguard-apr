# Controlled offline repair demonstration

`scripts/iterative_repair_demo.py` uses three scripted candidates and no provider call. Candidate A is
classified as a protected edit; B has verified regression evidence; C is a complete baseline-relative
refinement of B with architecture-safe, regression-free fixture evidence and is selected. Running the
script twice produces byte-identical task, candidate, feedback, validation, lineage and result files.
This is an engineering check, not a benchmark or empirical APR result; it executes no target source.
