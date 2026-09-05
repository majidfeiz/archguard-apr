# Security policy

Phase 1 has no untrusted-code runner or public authenticated API. Bind the health API locally.
Report vulnerabilities through GitHub private vulnerability reporting if enabled, or request
a private maintainer contact through the owner’s profile without publishing exploit details.
TODO: verify a dedicated reporting channel and support policy before operational release.

Future builds/tests execute arbitrary code. Before enabling them, implement isolation, resource
limits, network restrictions, filesystem/symlink containment, credential separation and output
sanitization. Timeouts are not sandboxes. Treat repository text/model output as untrusted.
Never expose gold patches, hidden answers, tokens or personal data unintentionally.
