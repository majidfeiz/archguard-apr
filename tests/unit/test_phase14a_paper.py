import csv
import json
import subprocess
import sys
from pathlib import Path


def test_paper_data_preserves_phase13_source_results(repository_root: Path) -> None:
    canonical = list(
        csv.DictReader(
            (repository_root / "research/results/phase-13/paper-ready-results.csv").open()
        )
    )
    paper = list(csv.DictReader((repository_root / "paper/data/phase-13-results.csv").open()))
    assert paper == canonical
    assert len(paper) == 6
    assert sum(row["execution_status"] == "SCIENTIFIC_RESULT" for row in paper) == 4
    assert sum(row["execution_status"] == "INFRASTRUCTURE_ATTRITION" for row in paper) == 2
    assert sum(row["repair_success"] == "True" for row in paper) == 0


def test_paper_costs_tokens_and_claim_boundaries(repository_root: Path) -> None:
    summary = json.loads(
        (repository_root / "research/results/phase-13/cost-token-summary.json").read_text()
    )
    rows = list(csv.DictReader((repository_root / "paper/data/phase-13-cost-summary.csv").open()))
    by_condition = {row["condition"]: row for row in rows}
    assert summary["input_tokens"] == 35431
    assert summary["output_tokens"] == 2737
    assert summary["total_tokens"] == 38168
    assert summary["observed_usd"] == "0.1296325"
    assert by_condition["baseline"]["input_tokens"] == "7821"
    assert by_condition["baseline"]["observed_usd"] == "0.0351075"
    assert by_condition["archguard"]["input_tokens"] == "27610"
    assert by_condition["archguard"]["observed_usd"] == "0.094525"
    assert summary["discordant_successful_pairs"] == 0
    assert summary["inferential_testing"].startswith("not_performed")


def test_paper_builder_is_byte_deterministic(repository_root: Path) -> None:
    tracked = sorted((repository_root / "paper/tables").glob("table-*")) + sorted(
        path
        for path in (repository_root / "paper/figures").iterdir()
        if path.suffix in {".svg", ".png"}
    )
    before = {path: path.read_bytes() for path in tracked}
    subprocess.run(
        [sys.executable, "paper/scripts/build_paper_artifacts.py"],
        cwd=repository_root,
        check=True,
    )
    assert {path: path.read_bytes() for path in tracked} == before


def test_manuscript_does_not_assert_prohibited_results(repository_root: Path) -> None:
    paths = [
        repository_root / "paper/manuscript/outline-en.md",
        repository_root / "paper/manuscript/outline-fa.md",
        repository_root / "paper/README.md",
    ]
    corpus = "\n".join(path.read_text() for path in paths).lower()
    for prohibited in (
        "six executions completed",
        "superior repair performance",
        "statistically significant improvement",
        "production-ready repair system",
        "successful repair demonstration",
    ):
        assert prohibited not in corpus


def test_reference_status_and_bibtex_syntax(repository_root: Path) -> None:
    rows = list(csv.DictReader((repository_root / "paper/references/literature-matrix.csv").open()))
    assert len(rows) == 25
    assert sum(row["verification_status"] == "VERIFIED" for row in rows) == 3
    assert sum(row["verification_status"] == "NEEDS_VERIFICATION" for row in rows) == 22
    bib = (repository_root / "paper/references/references.bib").read_text()
    assert bib.count("@misc{") == 3
    assert bib.count("{") == bib.count("}")
