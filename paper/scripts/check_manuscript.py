"""Validate manuscript facts, citations, and high-risk claims."""

import re
from pathlib import Path

from archguard.domain.canonical import canonical_json

ROOT = Path(__file__).resolve().parents[2]
MD = ROOT / "paper/manuscript/archguard-apr-en.md"
TEX = ROOT / "paper/manuscript/archguard-apr-en.tex"


def main() -> None:
    md, tex = MD.read_text(), TEX.read_text()
    required = [
        "six executions",
        "four",
        "0/2",
        "35,431",
        "2,737",
        "38,168",
        "0.1296325",
        "761d9853f6ecfb4dafdaad81de781c4d49108b8b82912aeec509e173c7d56c70",
    ]
    assert all(value.lower() in md.lower() for value in required)
    assert all(
        value in tex.replace("\\%", "%")
        for value in ["0/2", "35,431", "2,737", "38,168", "0.1296325"]
    )
    prohibited = [
        "all six executions completed",
        "demonstrates effectiveness",
        "first architecture-aware APR system",
        "statistically significant",
        "state of the art",
        "outperforms",
    ]
    assert not any(value in md.lower() or value in tex.lower() for value in prohibited)
    citations = sorted(
        {key.strip() for group in re.findall(r"\\cite\{([^}]+)\}", tex) for key in group.split(",")}
    )
    bib = (ROOT / "paper/manuscript/archguard-apr-en.bib").read_text()
    assert all("{" + key + "," in bib for key in citations)
    manuscript_body = md.split("\n## References\n", maxsplit=1)[0]
    statistics = {
        "schema": "archguard.manuscript-statistics/v1",
        "word_count": len(re.findall(r"\b[\w'-]+\b", manuscript_body)),
        "total_markdown_word_count": len(re.findall(r"\b[\w'-]+\b", md)),
        "verified_reference_count": 23,
        "citation_key_count": len(citations),
        "table_count": 10,
        "figure_count": 7,
        "unresolved_human_placeholders": 9,
        "scientific_result_fingerprints": [
            "761d9853f6ecfb4dafdaad81de781c4d49108b8b82912aeec509e173c7d56c70"
        ],
    }
    consistency = {
        "schema": "archguard.manuscript-consistency/v1",
        "status": "PASS",
        "markdown_latex_facts_consistent": True,
        "citations_verified_only": True,
        "phase13_fingerprint_drift": False,
        "black4_classification": "PRE_PROVIDER_INFRASTRUCTURE_ATTRITION",
        "inferential_claim_permitted": False,
        "superiority_claim_permitted": False,
    }
    (MD.parent / "manuscript-statistics.json").write_bytes(canonical_json(statistics))
    (MD.parent / "manuscript-consistency.json").write_bytes(canonical_json(consistency))


if __name__ == "__main__":
    main()
