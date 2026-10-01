# Live provider testing

Ordinary CI is fully offline. Live tests require the provider-specific run flag, an API key, a model,
and `ARCHGUARD_ACKNOWLEDGE_PROVIDER_COST=1`. They must use a small non-sensitive fixture and minimal
limits. API usage can incur cost. Raw content is not recorded by default.

Absent those values, status is: **Not executed — credentials/cost acknowledgement not provided.**
Consumer ChatGPT or Claude subscriptions do not provide API credentials.
