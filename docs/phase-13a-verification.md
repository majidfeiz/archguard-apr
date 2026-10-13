# Phase 13A provider preflight

The frozen provider configuration selects `gpt-5.4-2026-03-05` at
`https://api.openai.com/v1/responses`. Official OpenAI documentation was verified at
`2026-10-13T06:56:08Z`: the model has a 1,050,000-token context window, a 128,000-token maximum
output, structured-output support, and standard prices per one million tokens of USD 2.50 input,
USD 0.25 cached input, and USD 15.00 output.

Source: <https://developers.openai.com/api/docs/models/gpt-5.4>

The experiment configuration caps each request at 40,000 input and 8,000 output tokens. The
conservative maximum is USD 0.22 per call, USD 1.32 for the six primary executions, and USD 2.64 if
all six conditional infrastructure retries occur. The prospective five-dollar amendment freezes an
application hard ceiling of USD 4.50, an emergency scheduling threshold of USD 4.00, and a USD 0.50
safety margin. Retries are opportunistic and require the next projected total to remain within the
hard ceiling. Seed is recorded as unsupported by this endpoint/model configuration and is omitted.

The researcher should also configure an OpenAI project hard spend limit of USD 5.00 when the
platform supports it. Provider-side enforcement and prepaid balance reporting may be delayed, so the
application-level USD 4.50 ceiling remains authoritative and no auto-reload is assumed.

Run the offline preflight on the required Linux x86_64 host with Docker available and the key present:

```console
uv run archguard experiment provider-preflight \
  --config configs/experiments/phase13-provider.json \
  --output-directory /tmp/archguard-phase13-output
```

This command never contacts the provider. Phase 13A does not run the scientific experiment.
The provider decision and configuration fingerprint are recorded in `research/readiness-facts.json`;
the Phase 13 readiness gate is therefore operationally ready when the frozen files remain intact.
