# License registry v1

`archguard.license-registry/v1` is a canonical, source-free factual audit. Each record identifies a
framework, dataset, or upstream project by official HTTPS URL and immutable locator, then records the
official license path and raw-file SHA-256 when one exists. SPDX is allowed only with an unambiguous
official license file. Redistribution, benchmark use, and source execution are separate conclusions.
`VERIFIED`, `UNRESOLVED`, and `INELIGIBLE` are the only audit states. Absence is `UNRESOLVED`.

The top-level fingerprint is SHA-256 over canonical JSON without the `fingerprint` member. This is a
research-governance record, not legal advice, and contains no third-party license text.
