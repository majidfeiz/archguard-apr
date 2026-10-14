# Phase 14D–14E verification

Phase 14D–14E produces English and Persian author-manuscript sources and A4 Word/PDF editions. Majid
Feiz Deilami is the sole and corresponding author. The files state that they are author manuscripts
and have not been peer reviewed.

The publication builder validates 23 verified bibliography records, 23 resolved English citation
keys, Persian numeric citations 1–23, immutable Phase 13 counts, tokens, costs, classifications, and
fingerprints. It fails on missing inputs, unresolved placeholders, prohibited claims, empty figures,
or unreadable outputs. DOCX is generated with controlled metadata and A4 section geometry. PDF is
exported through Microsoft Word; PDF byte identity is not claimed because the exporter may include
variable metadata.

The focused equivalence repair adds a deterministic 49-row English–Persian section matrix in CSV and
Markdown. The publication counters report 6,606 English and 6,247 Persian words. All 49 headings,
23 references, 10 unique tables, seven figures, frozen facts, and required scientific topics are
represented in both editions; no matrix row remains compressed or missing.

Visual QA rendered every page of both PDFs. The PDF pages are also the independent visual rendering
of the corresponding DOCX export path. The review checked shaping, bidi behavior, margins, headers,
footers, page numbers, section continuity, citations, references, diagrams, tables, hashes, and blank
pages. Derived page images remain in temporary storage and are not committed.

The publication-layout repair replaced the generic justified title metadata with dedicated centered
English and Persian title blocks. It uses a controlled 20 pt title, intact author/status lines,
naturally wrapped affiliations, separate email and linked ORCID paragraphs, subdued manuscript-status
text, and a different first-page header configuration. Pages 1–2 were inspected at 220 DPI and every
remaining page was checked by contact sheet. The repair changed layout only; bilingual scientific
content, citations, evidence, tables, figures, bibliography, and author identity remained unchanged.

The rebuilt English editions contain 29 A4 pages each and the Persian editions contain 20 A4 pages
each. Arial was selected for Persian as the trusted installed fallback because Vazirmatn, Noto Naskh
Arabic, and Noto Sans Arabic were unavailable. No font was downloaded. All 20 Persian pages were
inspected for shaping, RTL flow, punctuation, citations, Latin identifiers, email/ORCID, widths,
captions, page breaks, references, omissions, blank pages, clipping, and overlap.

Scientific evidence did not change. No experiment, benchmark, repair agent, Docker workload, network
request, provider request, or GitHub Actions workflow ran.

Open human decisions are target venue selection, venue-template adaptation, final bilingual language
review, accessibility review, citation-context review, and submission packaging.
