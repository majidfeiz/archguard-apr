import csv
import hashlib
import json
import re
from pathlib import Path

import yaml


def test_release_gate_fails_closed_for_historical_privacy(repository_root: Path) -> None:
    gate = json.loads((repository_root / "release/public-release-gate.json").read_text())
    assert gate["status"] == "BLOCKED"
    assert gate["checks"]["history_privacy"] == "BLOCKED"
    assert gate["phase13_modified"] is False
    assert gate["blocking_findings"]


def test_public_manifest_hashes_match_publication_files(repository_root: Path) -> None:
    manifest = json.loads((repository_root / "release/public-artifact-manifest.json").read_text())
    hashed = {item["path"]: item["sha256"] for item in manifest["artifacts"] if "sha256" in item}
    for relative, expected in hashed.items():
        assert hashlib.sha256((repository_root / relative).read_bytes()).hexdigest() == expected


def test_citation_metadata_matches_package(repository_root: Path) -> None:
    citation = yaml.safe_load((repository_root / "CITATION.cff").read_text())
    package = (repository_root / "pyproject.toml").read_text()
    author = citation["authors"][0]
    assert citation["version"] == "0.12.8"
    assert 'version = "0.12.8"' in package
    assert author["given-names"] == "Majid"
    assert author["family-names"] == "Feiz Deilami"
    assert author["email"] == "majid.feiz@iau.ir"
    assert "doi" not in citation


def test_readme_local_links_resolve(repository_root: Path) -> None:
    readme = (repository_root / "README.md").read_text()
    targets = re.findall(r"\[[^]]+]\(([^)]+)\)", readme)
    local = [
        target.split("#", 1)[0]
        for target in targets
        if not target.startswith(("http://", "https://"))
    ]
    assert local
    assert all((repository_root / target).exists() for target in local)


def test_release_inventory_is_source_free(repository_root: Path) -> None:
    with (repository_root / "release/replication-package-inventory.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    restricted = {row["path"] for row in rows if row["included"] == "false"}
    assert {"benchmark repositories", "gold patches", "raw provider responses"} <= restricted
    assert all(row["source_free"] == "true" for row in rows if row["included"] == "true")


def test_current_decision_record_has_only_public_contact(repository_root: Path) -> None:
    decisions = json.loads(
        (repository_root / "paper/manuscript/manuscript-decisions.json").read_text()
    )
    assert decisions["email"] == "majid.feiz@iau.ir"
    assert "orcid_private_email" not in decisions
