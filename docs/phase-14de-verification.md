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

Visual QA rendered every page of both PDFs. The PDF pages are also the independent visual rendering
of the corresponding DOCX export path. The review checked shaping, bidi behavior, margins, headers,
footers, page numbers, section continuity, citations, references, diagrams, tables, hashes, and blank
pages. Derived page images remain in temporary storage and are not committed.

Scientific evidence did not change. No experiment, benchmark, repair agent, Docker workload, network
request, provider request, or GitHub Actions workflow ran.

Open human decisions are target venue selection, venue-template adaptation, final bilingual language
review, accessibility review, citation-context review, and submission packaging.
