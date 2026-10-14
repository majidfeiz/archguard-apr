import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path


def test_bilingual_publication_sources_validate(repository_root: Path) -> None:
    result = subprocess.run(
        [sys.executable, "paper/scripts/build_publication_documents.py", "--format", "validate"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    assert report["status"] == "PASS"
    assert report["verified_references"] == 23
    assert report["citation_keys"] == 23
    assert report["figures"] == 7
    assert report["tables"] == 10


def test_section_equivalence_matrix_is_current(repository_root: Path) -> None:
    result = subprocess.run(
        [sys.executable, "paper/scripts/check_bilingual_equivalence.py", "--check"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "PASS: 49 paired sections" in result.stdout
    matrix = (repository_root / "paper/manuscript/en-fa-section-equivalence.csv").read_text()
    assert "compressed-review-required" not in matrix
    assert matrix.count("equivalent") == 49


def test_persian_has_complete_citation_table_and_figure_parity(repository_root: Path) -> None:
    persian = (repository_root / "paper/manuscript/archguard-apr-fa.md").read_text()
    assert {int(value) for value in re.findall(r"\[(\d+)]", persian)} == set(range(1, 24))
    assert len(set(re.findall(r"\.\./tables/(table-[^)]+)", persian))) == 10
    assert sum(line.startswith("![شکل ") for line in persian.splitlines()) == 7
    assert all(marker in persian for marker in ("۳۵٬۴۳۱", "۲٬۷۳۷", "۰٫۱۲۹۶۳۲۵", "۳۳٫۳"))


def test_author_metadata_and_disclosures_are_final(repository_root: Path) -> None:
    english = (repository_root / "paper/manuscript/archguard-apr-en.md").read_text()
    persian = (repository_root / "paper/manuscript/archguard-apr-fa.md").read_text()
    decisions = json.loads(
        (repository_root / "paper/manuscript/manuscript-decisions.json").read_text()
    )
    assert decisions["author"] == "Majid Feiz Deilami"
    assert decisions["authorship"] == "sole and corresponding author"
    assert "majid.feiz@iau.ir" in english and "majid.feiz@iau.ir" in persian
    assert "This research received no external funding." in english
    assert "این پژوهش هیچ‌گونه حمایت مالی خارجی دریافت نکرده است." in persian
    assert "HUMAN_CONFIRMATION_REQUIRED" not in english + persian


def test_publication_documents_are_structurally_readable(repository_root: Path) -> None:
    dist = repository_root / "paper/dist"
    manifest = json.loads((dist / "document-build-manifest.json").read_text())
    assert manifest["phase13_modified"] is False
    assert manifest["provider_calls"] == 0
    assert manifest["fonts"]["persian"] == "Arial"
    for name in ("ArchGuard-APR-English.docx", "ArchGuard-APR-Persian.docx"):
        with zipfile.ZipFile(dist / name) as archive:
            names = set(archive.namelist())
            assert "word/document.xml" in names
            assert "word/header1.xml" in names
            assert "word/footer1.xml" in names
    for name in ("ArchGuard-APR-English.pdf", "ArchGuard-APR-Persian.pdf"):
        assert (dist / name).read_bytes().startswith(b"%PDF-")


def test_phase13_facts_and_no_overclaim_are_equivalent(repository_root: Path) -> None:
    corpus = "\n".join(
        (repository_root / path).read_text()
        for path in (
            "paper/manuscript/archguard-apr-en.md",
            "paper/manuscript/archguard-apr-fa.md",
        )
    )
    for value in ("0.1296325", "۰٫۱۲۹۶۳۲۵", "38,168", "۳۸٬۱۶۸"):
        assert value in corpus
    assert "all six executions completed" not in corpus.lower()
    assert "statistically significant" not in corpus.lower()
    assert "ریزش زیرساختی" in corpus
