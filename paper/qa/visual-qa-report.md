# Bilingual publication visual QA

Result: PASS after completing Persian section equivalence and removing raw Markdown link targets from
rendered prose. Inspection date: 2026-10-14. Temporary render root: `/tmp/archguard-fa-final-pages`.

| Edition | Source path | Pages | Page size | Inspection |
|---|---|---:|---|---|
| English DOCX | `paper/dist/ArchGuard-APR-English.docx` | 29 | A4 | PASS via independent Word PDF export |
| English PDF | `paper/dist/ArchGuard-APR-English.pdf` | 29 | A4 | PASS |
| Persian DOCX | `paper/dist/ArchGuard-APR-Persian.docx` | 20 | A4 | PASS via independent Word PDF export |
| Persian PDF | `paper/dist/ArchGuard-APR-Persian.pdf` | 20 | A4 | PASS via Poppler render at 90 DPI |

Every page of both Persian output paths was inspected individually. The Word PDF export is the
independent visual render of the Persian DOCX; the final PDF was rendered with Poppler at 90 DPI.
No missing or clipped body text, overlap, unexpected blank page, broken Persian shaping, reversed
punctuation, margin overflow, header/footer collision, or unresolved placeholder was observed. Latin
emails, ORCID, URLs, hashes, model identifiers, costs, and citations remain readable within Persian
paragraphs. Compact source-free diagrams use textual flows and numerical summaries, so they remain
legible without external image dependencies. References fit within the page margins.

The derived page previews are excluded from Git to avoid committing 80 redundant raster files. Their
page counts are recorded in `visual-qa-summary.json`. The selected Persian font is Arial because
Vazirmatn, Noto Naskh Arabic, and Noto Sans Arabic were not installed; no font was downloaded.
