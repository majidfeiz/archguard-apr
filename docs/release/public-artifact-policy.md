# Public artifact policy

| Classification | Content | Rule |
|---|---|---|
| safe for public release | source code, tests, synthetic fixtures, architecture profiles, configuration templates | publish after security and license review |
| public with attribution/license | manuscripts, original figures/tables, third-party citations, dependencies | preserve scoped licenses and attribution |
| generated but safe | canonical source-free results, paper aggregates, tracked DOCX/PDF files | verify hashes and provenance |
| private/restricted | credentials, raw provider responses, benchmark source, gold patches, evaluator-only assets, unredacted logs | never commit or package |
| excluded from Git | `.env`, local caches, worktrees, benchmark checkouts, raw patches, external evidence ZIPs | retain only in controlled external storage |
| accepted personal disclosure | author-owned historical personal email | retain only under the scoped author decision; never generalize to secrets or third-party data |
| unresolved/manual review | action pinning, final archive composition, rights for any newly introduced external payload | block publication until resolved |

Source-free means that an artifact contains no target source, patch hunks, prompt, provider response, credential, private path, or hidden answer. A hash or identifier does not by itself establish redistribution permission.
