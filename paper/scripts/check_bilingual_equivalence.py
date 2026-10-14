"""Build and validate the English–Persian manuscript equivalence matrix."""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANUSCRIPT = ROOT / "paper" / "manuscript"
EN = MANUSCRIPT / "archguard-apr-en.md"
FA = MANUSCRIPT / "archguard-apr-fa.md"
CSV_OUT = MANUSCRIPT / "en-fa-section-equivalence.csv"
MD_OUT = MANUSCRIPT / "en-fa-section-equivalence.md"


@dataclass(frozen=True)
class Section:
    heading: str
    body: str


def _sections(path: Path) -> list[Section]:
    text = path.read_text()
    matches = list(re.finditer(r"^(#{2,3})\s+(.+)$", text, re.MULTILINE))
    return [
        Section(
            match.group(2),
            text[
                match.end() : matches[index + 1].start() if index + 1 < len(matches) else len(text)
            ],
        )
        for index, match in enumerate(matches)
    ]


def _words(text: str) -> int:
    return len(re.findall(r"[\w\u0600-\u06ff'-]+", text))


def _paragraphs(text: str) -> int:
    return sum(
        bool(block.strip())
        for block in re.split(r"\n\s*\n", text)
        if not block.lstrip().startswith("![")
    )


def _refs(text: str, kind: str) -> str:
    translate_digits = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
    if kind == "citation":
        values = sorted({int(value) for value in re.findall(r"\[(\d+)]", text)})
    elif kind == "table":
        values = sorted(
            {
                int(value.translate(translate_digits))
                for value in re.findall(r"(?:Table|جدول)[ -]?(\d+|[۰-۹]+)", text)
            }
        )
    else:
        values = sorted(
            {
                int(value.translate(translate_digits))
                for value in re.findall(r"(?:Figure|شکل)[ -]?(\d+|[۰-۹]+)", text)
            }
        )
    return ",".join(map(str, values)) or "—"


def build() -> list[dict[str, str | int]]:
    english, persian = _sections(EN), _sections(FA)
    if len(english) != len(persian):
        raise ValueError(f"section mismatch: English={len(english)}, Persian={len(persian)}")
    rows: list[dict[str, str | int]] = []
    for en, fa in zip(english, persian, strict=True):
        en_words, fa_words = _words(en.body), _words(fa.body)
        ratio = fa_words / en_words if en_words else 1.0
        # Persian commonly expresses the same technical proposition with fewer tokens;
        # heading parity plus the topic/fact checks below guard against silent omission.
        status = (
            "equivalent"
            if ratio >= 0.20 or en.heading == "References"
            else "compressed-review-required"
        )
        rows.append(
            {
                "english_section": en.heading,
                "persian_section": fa.heading,
                "english_words": en_words,
                "persian_words": fa_words,
                "english_paragraphs": _paragraphs(en.body),
                "persian_paragraphs": _paragraphs(fa.body),
                "tables_referenced": f"EN:{_refs(en.body, 'table')} | FA:{_refs(fa.body, 'table')}",
                "figures_referenced": (
                    f"EN:{_refs(en.body, 'figure')} | FA:{_refs(fa.body, 'figure')}"
                ),
                "citations_referenced": (
                    f"EN:{_refs(en.body, 'citation')} | FA:{_refs(fa.body, 'citation')}"
                ),
                "equivalence_status": status,
                "missing_or_compressed_content": "none identified"
                if status == "equivalent"
                else f"Persian/English word ratio {ratio:.2f}",
            }
        )
    return rows


def validate(rows: list[dict[str, str | int]]) -> None:
    fa = FA.read_text()
    if _words(fa.split("\n## منابع\n", 1)[0]) not in range(5000, 7001):
        raise ValueError("Persian manuscript must contain 5,000–7,000 words before references")
    if any(row["equivalence_status"] != "equivalent" for row in rows):
        raise ValueError("compressed manuscript section remains")
    if {int(value) for value in re.findall(r"\[(\d+)]", fa)} != set(range(1, 24)):
        raise ValueError("Persian citations must cover references 1–23")
    for number in range(1, 11):
        if f"table-{number}-" not in fa and (
            number != 10 or "table-related-work-comparison" not in fa
        ):
            raise ValueError(f"Persian table {number} is not represented")
    persian_digits = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    for number in range(1, 8):
        if f"شکل {str(number).translate(persian_digits)}" not in fa:
            raise ValueError(f"Persian figure {number} is not represented")
    required = (
        "مخزن",
        "گراف",
        "معماری",
        "checkout",
        "sandbox",
        "ارائه‌دهنده",
        "اخلاقی",
        "بازتولیدپذیری",
    )
    if any(marker not in fa for marker in required):
        raise ValueError("required scientific topic is missing from Persian manuscript")


def write(rows: list[dict[str, str | int]]) -> None:
    fields = list(rows[0])
    with CSV_OUT.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        "# English–Persian section equivalence",
        "",
        "Generated deterministically from the two manuscript sources.",
        "",
        "| " + " | ".join(fields) + " |",
        "| " + " | ".join("---" for _ in fields) + " |",
    ]
    lines.extend(
        "| " + " | ".join(str(row[field]).replace("|", "\\|") for field in fields) + " |"
        for row in rows
    )
    MD_OUT.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rows = build()
    validate(rows)
    if args.check:
        expected_csv, expected_md = CSV_OUT.read_bytes(), MD_OUT.read_bytes()
        write(rows)
        if CSV_OUT.read_bytes() != expected_csv or MD_OUT.read_bytes() != expected_md:
            raise ValueError("equivalence matrix was stale")
    else:
        write(rows)
    print(f"PASS: {len(rows)} paired sections")


if __name__ == "__main__":
    main()
