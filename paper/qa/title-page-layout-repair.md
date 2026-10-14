# Bilingual title-page layout repair

Inspection date: 2026-10-14. Scope: presentation and document-generation behavior only; manuscript prose, citations, results, tables, figures, bibliography, author identity, and Phase 13 evidence were unchanged.

## Before

The generic Markdown paragraph path applied full justification to title-page metadata. In the English edition, this spread the author name and academic status across the measure, fragmented the affiliation, and split the ORCID. The title used uncontrolled wrapping, and the default running header appeared on page 1. The Persian edition inherited the same paragraph behavior, causing fragmented RTL metadata and unstable Latin identifiers.

## After

The generator now emits a dedicated centered bilingual title block. The English 20 pt title uses controlled lines and keeps `Architecture-Constraint-Aware` intact. Author, academic status, affiliation, email, ORCID, and manuscript status each have an explicit centered paragraph with normal word spacing. The ORCID is a stable single-line hyperlink. The Persian block uses RTL-aware centered paragraphs, intact shaping, naturally wrapped affiliation, separate email and ORCID lines, and an upright status line to avoid unreliable Arabic-script italic rendering. OOXML uses a different first page so the running header begins on page 2 while page numbering remains intact.

## Visual verification

Microsoft Word exported each DOCX to its canonical PDF, providing the independent DOCX rendering path used by this repository. Poppler rendered every page at normal scale and pages 1–2 at 220 DPI. The packaged `render_docx.py` path was also attempted, but its required `pdf2image` and LibreOffice runtime were unavailable; no dependency or network access was added.

- English DOCX/PDF: 29 A4 pages each.
- Persian DOCX/PDF: 20 A4 pages each.
- Pages 1–2: author names, academic status, affiliations, emails, linked ORCIDs, status lines, title wrapping, Abstract placement, headers, footers, and margins passed normal and zoomed inspection.
- Remaining pages: contact-sheet inspection found no clipping, overlap, unexpected blank page, margin overflow, broken shaping, table/figure regression, or header/footer collision.
- Fonts: Times New Roman for English; Arial for Persian. No font was downloaded or embedded from a third party.

Result: **PASS**.
