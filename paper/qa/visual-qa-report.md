# Bilingual publication visual QA

Result: PASS after correction of literal HTML line breaks, Persian result-table layout, and document
headers/footers. Inspection date: 2026-10-14. Temporary render root: `/tmp/archguard-14de`.

| Edition | Source path | Pages | Page size | Inspection |
|---|---|---:|---|---|
| English DOCX | `paper/dist/ArchGuard-APR-English.docx` | 29 | A4 | PASS via independent Word PDF export |
| English PDF | `paper/dist/ArchGuard-APR-English.pdf` | 29 | A4 | PASS |
| Persian DOCX | `paper/dist/ArchGuard-APR-Persian.docx` | 11 | A4 | PASS via independent Word PDF export |
| Persian PDF | `paper/dist/ArchGuard-APR-Persian.pdf` | 11 | A4 | PASS |

Every page was rendered at 110 DPI and inspected individually and in full-document contact sheets.
No missing or clipped body text, overlap, unexpected blank page, broken Persian shaping, reversed
punctuation, margin overflow, header/footer collision, or unresolved placeholder was observed. Latin
emails, ORCID, URLs, hashes, model identifiers, costs, and citations remain readable within Persian
paragraphs. Compact source-free diagrams use textual flows and numerical summaries, so they remain
legible without external image dependencies. References fit within the page margins.

The derived page previews are excluded from Git to avoid committing 80 redundant raster files. Their
page counts and aggregate hashes are recorded in `visual-qa-summary.json`.
