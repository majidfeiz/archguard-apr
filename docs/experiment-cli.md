# Experiment CLI

Validate plans/contracts and create an immutable deterministic schedule:

```bash
archguard experiment plan validate --plan configs/experiments/phase12-plan.yaml
archguard experiment compare validate --contract contract.json
archguard experiment schedule create --plan PLAN --contract CONTRACT --output SCHEDULE
archguard experiment run --schedule SCHEDULE --mode offline
archguard experiment ledger verify --ledger LEDGER
archguard experiment export --experiment LEDGER --format csv --output RESULTS
```

External mode requires `--acknowledge-resources`; live mode requires both
`--acknowledge-provider-cost` and `--acknowledge-benchmark-use`. These commands perform a safe dry-run
and never accept API keys. Exit 2 means invalid input, 3 unfair comparison, 4 immutable output conflict,
and 5 missing authorization. CSV columns are fixed and outputs contain no source, raw prompts or gold.
