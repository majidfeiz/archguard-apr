# Bilingual publication visual QA

Result: PASS after the bilingual title-page layout repair. Inspection date: 2026-10-14. Temporary
render root: `/tmp/archguard-title-qa-final`.

| Edition | Source path | Pages | Page size | Inspection |
|---|---|---:|---|---|
| English DOCX | `paper/dist/ArchGuard-APR-English.docx` | 29 | A4 | PASS via Microsoft Word PDF export; pages 1–2 at 220 DPI |
| English PDF | `paper/dist/ArchGuard-APR-English.pdf` | 29 | A4 | PASS via Poppler; pages 1–2 at 220 DPI |
| Persian DOCX | `paper/dist/ArchGuard-APR-Persian.docx` | 20 | A4 | PASS via Microsoft Word PDF export; pages 1–2 at 220 DPI |
| Persian PDF | `paper/dist/ArchGuard-APR-Persian.pdf` | 20 | A4 | PASS via Poppler; pages 1–2 at 220 DPI |

Every page of all four output paths was inspected through normal-scale contact sheets. The Word PDF
exports are the visual render of the DOCX paths; both canonical PDFs were independently rasterized
with Poppler. Pages 1–2 of every edition were additionally inspected at 220 DPI.
The repaired title blocks have centered metadata with normal spacing, intact author names and
affiliations, unsplit linked ORCIDs, intact emails, balanced title lines, subdued status text, and no
first-page running header. Abstract headings begin cleanly below the metadata. No missing or clipped
body text, overlap, unexpected blank page, broken Persian shaping, bidi defect, margin overflow,
header/footer collision, or unresolved placeholder was observed. Tables, figures, citations,
references, hashes, identifiers, costs, and page numbering remain legible.

The derived page previews are excluded from Git. Their page counts and title-page checks are recorded
in `visual-qa-summary.json`; repair details are in `title-page-layout-repair.md`. The selected Persian font is Arial because
Vazirmatn, Noto Naskh Arabic, and Noto Sans Arabic were not installed; no font was downloaded.
