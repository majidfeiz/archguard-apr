"""Build deterministic Phase 14A publication tables and figures."""

import csv
import json
import struct
import zlib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / "paper"
RESULTS = ROOT / "research/results/phase-13"
SOURCE_SHA = "48080661ddbff3e486d47cebc63754e29d4dd4664febbb7f8143484e4c03e99d"
MANIFEST_SHA = "8afb87add96e29898ae712f8ef08928b9ba1290a0aabc3ce34bac82adb4b86c2"
IMPORT_SHA = "80eac046fc614cad1beb7de127ba69aa907b5c588d5409c30e92e5b685c0dc28"


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_table(name: str, title: str, rows: list[dict[str, Any]]) -> None:
    write_csv(PAPER / "tables" / f"{name}.csv", rows)
    headings = list(rows[0])
    lines = [
        f"# {title}",
        "",
        "| " + " | ".join(headings) + " |",
        "| " + " | ".join("---" for _ in headings) + " |",
    ]
    lines.extend("| " + " | ".join(str(row[key]) for key in headings) + " |" for row in rows)
    (PAPER / "tables" / f"{name}.md").write_text("\n".join(lines) + "\n")


def svg_bars(path: Path, title: str, labels: list[str], values: list[float], unit: str) -> None:
    maximum = max(values) or 1
    bars = []
    for index, (label, value) in enumerate(zip(labels, values, strict=True)):
        width = int(420 * value / maximum)
        y = 70 + index * 70
        bars.append(f'<text x="20" y="{y + 22}" font-size="16">{label}</text>')
        bars.append(f'<rect x="140" y="{y}" width="{width}" height="32" fill="#3569a8"/>')
        bars.append(f'<text x="{150 + width}" y="{y + 22}" font-size="15">{value:g} {unit}</text>')
    content = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="240">'
        '<rect width="100%" height="100%" fill="white"/>'
        f'<text x="20" y="32" font-size="20" font-weight="bold">{title}</text>'
        f"{''.join(bars)}"
        '<text x="20" y="225" font-size="12">'
        "Exploratory sample: two valid paired tasks</text></svg>\n"
    )
    path.write_text(content)


def png_bars(path: Path, values: list[float]) -> None:
    width, height = 640, 240
    pixels = bytearray([255] * width * height * 3)
    maximum = max(values) or 1
    for index, value in enumerate(values):
        x0, y0 = 150, 55 + index * 85
        x1 = x0 + int(400 * value / maximum)
        for y in range(y0, y0 + 42):
            for x in range(x0, x1):
                offset = (y * width + x) * 3
                pixels[offset : offset + 3] = bytes((53, 105, 168))
    raw = b"".join(b"\0" + pixels[y * width * 3 : (y + 1) * width * 3] for y in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def main() -> None:
    executions = list(csv.DictReader((RESULTS / "paper-ready-results.csv").open()))
    summary = json.loads((RESULTS / "cost-token-summary.json").read_text())
    attrition = json.loads((RESULTS / "attrition-report.json").read_text())
    (PAPER / "data").mkdir(parents=True, exist_ok=True)
    write_csv(PAPER / "data/phase-13-results.csv", executions)
    (PAPER / "data/phase-13-results.json").write_bytes(
        (RESULTS / "paper-ready-results.json").read_bytes()
    )
    write_csv(
        PAPER / "data/phase-13-cost-summary.csv",
        [{"condition": key, **value} for key, value in summary["conditions"].items()],
    )
    write_csv(
        PAPER / "data/phase-13-attrition.csv",
        [
            {
                "ordinals": "5;6",
                "task_id": attrition["task_id"],
                "classification": attrition["classification"],
                "stage": attrition["diagnostic"]["stage"],
                "exception_category": attrition["diagnostic"]["exception_category"],
                "diagnostic_fingerprint": attrition["diagnostic"]["diagnostic_fingerprint"],
            }
        ],
    )
    tables = {
        "table-1-system-components": (
            "Table 1 — System components and responsibilities",
            [
                {
                    "component": "Repository analysis",
                    "responsibility": "Deterministic AST snapshot analysis",
                },
                {
                    "component": "Repository graph",
                    "responsibility": "Validated immutable dependency graph",
                },
                {
                    "component": "Architecture constraints",
                    "responsibility": "Compile and evaluate explicit profiles",
                },
                {
                    "component": "Patch validation",
                    "responsibility": "Fail-closed patch policy enforcement",
                },
                {
                    "component": "Execution feedback",
                    "responsibility": "Sandboxed bounded evaluator results",
                },
                {
                    "component": "Orchestration",
                    "responsibility": "Deterministic agent-role state machine",
                },
            ],
        ),
        "table-2-research-questions": (
            "Table 2 — Research questions and evidence",
            [
                {"rq": "RQ1", "evidence": "Implementation, tests, canonical artifacts"},
                {"rq": "RQ2", "evidence": "Attrition and failure diagnostics"},
                {"rq": "RQ3", "evidence": "Four outcomes, tokens, and costs"},
            ],
        ),
        "table-3-qualified-population": (
            "Table 3 — Qualified task population",
            [
                {"task": "PySnooper-2", "project": "PySnooper", "phase13_status": "completed_pair"},
                {"task": "PySnooper-3", "project": "PySnooper", "phase13_status": "completed_pair"},
                {
                    "task": "black-4",
                    "project": "black",
                    "phase13_status": "infrastructure_attrition",
                },
            ],
        ),
        "table-4-per-execution-results": ("Table 4 — Per-execution Phase 13 results", executions),
        "table-5-paired-comparison": (
            "Table 5 — Paired baseline versus ArchGuard",
            [
                {
                    "task": task,
                    "baseline_success": False,
                    "archguard_success": False,
                    "discordant": False,
                }
                for task in ("PySnooper-2", "PySnooper-3")
            ],
        ),
        "table-6-token-cost": (
            "Table 6 — Token and cost comparison",
            [
                {
                    "condition": key,
                    "input_tokens": value["input_tokens"],
                    "output_tokens": value["output_tokens"],
                    "cost_usd": value["observed_usd"],
                }
                for key, value in summary["conditions"].items()
            ],
        ),
        "table-7-attrition": (
            "Table 7 — Infrastructure attrition",
            [
                {
                    "task": "black-4",
                    "ordinals": "5;6",
                    "stage": "checkout",
                    "classification": "pre-provider infrastructure attrition",
                }
            ],
        ),
        "table-8-threats": (
            "Table 8 — Threats to validity and mitigations",
            [
                {"threat": "Two valid pairs", "mitigation": "Descriptive reporting only"},
                {"threat": "One represented project", "mitigation": "No generalization claim"},
                {
                    "threat": "33.3% attrition",
                    "mitigation": "Separate infrastructure from repair outcomes",
                },
                {"threat": "Zero successes", "mitigation": "No superiority or significance claim"},
            ],
        ),
        "table-9-reproducibility": (
            "Table 9 — Reproducibility artifacts and fingerprints",
            [
                {
                    "artifact": "source",
                    "fingerprint": SOURCE_SHA,
                },
                {
                    "artifact": "manifest",
                    "fingerprint": MANIFEST_SHA,
                },
                {"artifact": "result", "fingerprint": summary["result_fingerprint"]},
                {
                    "artifact": "import",
                    "fingerprint": IMPORT_SHA,
                },
            ],
        ),
    }
    (PAPER / "tables").mkdir(parents=True, exist_ok=True)
    for name, (title, rows) in tables.items():
        write_table(name, title, rows)
    figures = PAPER / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    svg_bars(
        figures / "cost-comparison.svg",
        "Observed provider cost",
        ["Baseline", "ArchGuard"],
        [0.0351075, 0.094525],
        "USD",
    )
    png_bars(figures / "cost-comparison.png", [0.0351075, 0.094525])
    svg_bars(
        figures / "input-token-comparison.svg",
        "Input-token usage",
        ["Baseline", "ArchGuard"],
        [7821, 27610],
        "tokens",
    )
    png_bars(figures / "input-token-comparison.png", [7821, 27610])
    svg_bars(
        figures / "execution-outcomes.svg",
        "Execution accounting",
        ["Invalid patch", "Infrastructure attrition"],
        [4, 2],
        "executions",
    )
    png_bars(figures / "execution-outcomes.png", [4, 2])


if __name__ == "__main__":
    main()
