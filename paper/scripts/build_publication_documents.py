"""Validate and build the bilingual publication documents without scientific execution."""

# ruff: noqa: E501  # Long XML/HTML literals are kept intact for deterministic output.

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANUSCRIPT = ROOT / "paper" / "manuscript"
DIST = ROOT / "paper" / "dist"
EN = MANUSCRIPT / "archguard-apr-en.md"
FA = MANUSCRIPT / "archguard-apr-fa.md"
REFS = MANUSCRIPT / "archguard-apr-en.bib"
TITLE_EN = (
    "ArchGuard-APR: Architecture-Constraint-Aware Multi-Agent Program Repair Using "
    "Repository Graphs and Execution Feedback"
)
TITLE_FA = "ArchGuard-APR: تعمیر خودکار برنامه آگاه از قیود معماری با استفاده از گراف‌های مخزن و بازخورد اجرا"
AUTHOR_EN = "Majid Feiz Deilami"
AUTHOR_FA = "مجید فیض دیلمی"
ACADEMIC_STATUS_EN = "M.Sc. Student in Software Engineering"
ACADEMIC_STATUS_FA = "دانشجوی کارشناسی ارشد مهندسی نرم‌افزار"
AFFILIATION_EN = (
    "Department of Computer Engineering, Lahijan Branch, Islamic Azad University, Lahijan, Iran"
)
AFFILIATION_FA = "گروه مهندسی کامپیوتر، واحد لاهیجان، دانشگاه آزاد اسلامی، لاهیجان، ایران"
EMAIL = "majid.feiz@iau.ir"
ORCID_ID = "0009-0006-8439-1839"
ORCID_URL = f"https://orcid.org/{ORCID_ID}"
SUBJECT = "Architecture-aware automated program repair and exploratory feasibility evaluation"
KEYWORDS = (
    "automated program repair; software architecture; repository graph; architecture constraints; "
    "large language models; multi-agent systems; execution feedback; reproducibility"
)
FACTS = (
    "38,168",
    "0.1296325",
    "761d9853f6ecfb4dafdaad81de781c4d49108b8b82912aeec509e173c7d56c70",
    "421f3129ef6bee5883c41d05f087d6faff5b2a3de3b2ea543b4d27ade1488886",
    "eae1920ce71c025d2d94096798daf8b14df098249743631efe9a0aa7a541fbe8",
    "f5dc6fb5b8bf54c7cf1b58b990fa3db44073500df9903e3a7d93cbeb1ad92c2d",
)
FA_FACTS = ("۳۸٬۱۶۸", "۰٫۱۲۹۶۳۲۵", *FACTS[2:])
PROHIBITED = (
    "HUMAN_CONFIRMATION_REQUIRED",
    "all six executions completed",
    "statistically significant",
    "demonstrates effectiveness",
    "outperforms",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate() -> dict[str, int]:
    required = [EN, FA, REFS, MANUSCRIPT / "archguard-apr-en.tex"]
    for path in required:
        if not path.is_file() or not path.read_bytes():
            raise ValueError(f"missing or empty source: {path.relative_to(ROOT)}")
    en = EN.read_text()
    fa = FA.read_text()
    for fact in FACTS:
        if fact not in en:
            raise ValueError(f"English fact mismatch: {fact}")
    for fact in FA_FACTS:
        if fact not in fa:
            raise ValueError(f"Persian fact mismatch: {fact}")
    joined = f"{en}\n{fa}".lower()
    for marker in PROHIBITED:
        if marker.lower() in joined:
            raise ValueError(f"unresolved or prohibited claim: {marker}")
    refs = re.findall(r"^@\w+\{([^,]+),", REFS.read_text(), flags=re.MULTILINE)
    if len(refs) != 23 or len(set(refs)) != 23:
        raise ValueError("bibliography must contain exactly 23 unique verified records")
    cited = {
        key
        for group in re.findall(
            r"\\cite\{([^}]+)\}", (MANUSCRIPT / "archguard-apr-en.tex").read_text()
        )
        for key in group.split(",")
    }
    if cited != set(refs):
        raise ValueError("English citations do not resolve to all verified references")
    fa_citations = {int(value) for value in re.findall(r"\[(\d+)\]", fa)}
    if fa_citations != set(range(1, 24)):
        raise ValueError("Persian numeric citations do not resolve to references 1--23")
    for path in ROOT.joinpath("paper/figures").iterdir():
        if path.suffix in {".png", ".svg", ".mmd"} and not path.read_bytes():
            raise ValueError(f"empty figure: {path.name}")
    return {
        "verified_references": len(refs),
        "english_words": len(re.findall(r"\b[\w'-]+\b", en.split("\n## References\n", 1)[0])),
        "persian_words": len(re.findall(r"[\w\u0600-\u06ff]+", fa.split("\n## منابع\n", 1)[0])),
        "tables": 10,
        "figures": 7,
        "citation_keys": len(cited),
    }


def _inline(value: str) -> str:
    value = value.replace("<br>", "\n")
    value = re.sub(r"\[([^]]+)]\([^)]+\)", r"\1", value)
    value = html.escape(value)
    value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
    value = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", value)
    return value.replace("\n", "<br>")


def _markdown_html(source: Path, *, rtl: bool) -> str:
    lines = source.read_text().splitlines()
    first_section = next(index for index, line in enumerate(lines) if line.startswith("## "))
    lines = lines[first_section:]
    body: list[str] = []
    paragraph: list[str] = []
    table: list[list[str]] = []

    def flush_paragraph() -> None:
        if paragraph:
            body.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def flush_table() -> None:
        if not table:
            return
        rows = [row for row in table if not all(re.fullmatch(r":?-+:?", cell) for cell in row)]
        body.append("<table>")
        for index, row in enumerate(rows):
            tag = "th" if index == 0 else "td"
            body.append(
                "<tr>" + "".join(f"<{tag}>{_inline(cell)}</{tag}>" for cell in row) + "</tr>"
            )
        body.append("</table>")
        table.clear()

    for line in lines:
        if line.startswith("|") and line.endswith("|"):
            flush_paragraph()
            table.append([cell.strip() for cell in line.strip("|").split("|")])
            continue
        flush_table()
        image = re.fullmatch(r"!\[(.+)]\((.+)\)", line)
        if image:
            flush_paragraph()
            caption, target = image.groups()
            resolved = (source.parent / target).resolve()
            png = resolved.with_suffix(".png")
            if resolved.suffix.lower() == ".png" or png.is_file():
                summaries = {
                    "execution-outcomes": "Completed invalid patches: 4 | Infrastructure attrition: 2",
                    "cost-comparison": "Baseline: USD 0.0351075 | ArchGuard: USD 0.094525",
                    "input-token-comparison": "Baseline: 7,821 input tokens | ArchGuard: 27,610 input tokens",
                }
                body.append(
                    f'<figure class="diagram"><div>{_inline(summaries.get(resolved.stem, caption))}</div>'
                    f"<figcaption>{_inline(caption)}</figcaption></figure>"
                )
            else:
                labels = (
                    re.findall(r"\[([^]]+)]", resolved.read_text()) if resolved.is_file() else []
                )
                flow = " → ".join(labels) if labels else caption.split(";", 1)[0]
                body.append(
                    f'<figure class="diagram"><div>{_inline(flow)}</div><figcaption>{_inline(caption)}</figcaption></figure>'
                )
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)", line)
        if heading:
            flush_paragraph()
            level = min(len(heading.group(1)), 3)
            body.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
        elif line.startswith("- "):
            flush_paragraph()
            body.append(f"<p class=bullet>• {_inline(line[2:])}</p>")
        elif not line.strip():
            flush_paragraph()
        else:
            paragraph.append(line.strip())
    flush_paragraph()
    flush_table()
    lang = "fa" if rtl else "en"
    direction = "rtl" if rtl else "ltr"
    font = "Arial" if rtl else "Times New Roman"
    title = TITLE_FA if rtl else TITLE_EN
    author = AUTHOR_FA if rtl else AUTHOR_EN
    if rtl:
        title_lines = (
            '<span dir="ltr">ArchGuard-APR:</span> تعمیر خودکار برنامه آگاه از قیود معماری',
            "با استفاده از گراف‌های مخزن و بازخورد اجرا",
        )
        academic_status = ACADEMIC_STATUS_FA
        affiliation = AFFILIATION_FA
        email_label = "نویسنده مسئول"
        status = "نسخه نویسنده — داوری علمی نشده"
        status_markup = status
    else:
        title_lines = (
            "ArchGuard-APR:",
            "Architecture-Constraint-Aware",
            "Multi-Agent Program Repair Using Repository Graphs",
            "and Execution Feedback",
        )
        academic_status = ACADEMIC_STATUS_EN
        affiliation = AFFILIATION_EN
        email_label = "Corresponding author"
        status = "Author manuscript — not peer reviewed"
        status_markup = f"<em>{status}</em>"
    title_block = (
        '<header class="title-page">'
        f"<h1>{'<br>'.join(title_lines)}</h1>"
        f'<p class="author">{html.escape(author)}</p>'
        f'<p class="academic-status">{html.escape(academic_status)}</p>'
        f'<p class="affiliation">{html.escape(affiliation)}</p>'
        f'<p class="contact"><span>{html.escape(email_label)}: {EMAIL}</span></p>'
        f'<p class="orcid"><a href="{ORCID_URL}">ORCID: {ORCID_ID}</a></p>'
        f'<p class="manuscript-status">{status_markup}</p>'
        "</header>"
    )
    return f"""<!doctype html><html lang="{lang}" dir="{direction}"><head><meta charset="utf-8">
<meta name="author" content="{author}"><meta name="title" content="{html.escape(title)}">
<style>@page{{size:A4;margin:22mm 20mm 22mm 20mm}} body{{font-family:'{font}';font-size:11pt;line-height:1.45;direction:{direction};text-align:{"right" if rtl else "left"}}}
h1{{font-size:20pt;line-height:1.18;text-align:center;color:#000;margin:0 0 18pt;page-break-after:avoid}} h2{{font-size:14pt;color:#111;page-break-after:avoid}} h3{{font-size:12pt;color:#222;page-break-after:avoid}}
p{{text-align:justify;orphans:3;widows:3}} table{{border-collapse:collapse;width:100%;margin:10pt 0;page-break-inside:avoid}} th,td{{border:1px solid #777;padding:4pt;font-size:9pt;vertical-align:top}} th{{background:#d9eaf7}}
figure{{text-align:center;margin:12pt 0;page-break-inside:avoid}} img{{max-width:92%;max-height:14cm}} figcaption{{font-size:9pt;font-style:italic;margin-top:4pt}} .diagram div{{border:2px solid #365f91;background:#eef5fb;padding:18pt;border-radius:6pt}} code{{font-family:Menlo,monospace;font-size:8.5pt;overflow-wrap:anywhere}} .bullet{{margin-left:18pt}}
.title-page{{text-align:center;margin:10pt auto 20pt;page-break-inside:avoid}} .title-page p{{text-align:center !important;margin:0;line-height:1.25;word-spacing:normal}}
.title-page .author{{font-size:13pt;font-weight:bold;margin-top:3pt}} .title-page .academic-status{{font-size:11pt;margin-top:5pt}} .title-page .affiliation{{font-size:10.5pt;margin:5pt auto 0;max-width:150mm}}
.title-page .contact,.title-page .orcid{{font-size:10pt;margin-top:4pt;white-space:nowrap}} .title-page .manuscript-status{{font-size:9pt;margin-top:10pt;color:#222}}</style></head><body>{title_block}{"".join(body)}</body></html>"""


def _patch_docx(path: Path, *, rtl: bool) -> None:
    with tempfile.TemporaryDirectory() as temp:
        unpack = Path(temp)
        with zipfile.ZipFile(path) as archive:
            archive.extractall(unpack)
        core = unpack / "docProps/core.xml"
        text = core.read_text()
        replacements = {
            r"<dc:title>.*?</dc:title>": f"<dc:title>{html.escape(TITLE_FA if rtl else TITLE_EN)}</dc:title>",
            r"<dc:creator>.*?</dc:creator>": f"<dc:creator>{html.escape(AUTHOR_FA if rtl else AUTHOR_EN)}</dc:creator>",
            r"<dc:subject>.*?</dc:subject>": f"<dc:subject>{SUBJECT}</dc:subject>",
            r"<cp:keywords>.*?</cp:keywords>": f"<cp:keywords>{KEYWORDS}</cp:keywords>",
        }
        for pattern, replacement in replacements.items():
            if re.search(pattern, text):
                text = re.sub(pattern, replacement, text)
            else:
                text = text.replace("</cp:coreProperties>", replacement + "</cp:coreProperties>")
        core.write_text(text)
        document = unpack / "word/document.xml"
        xml = document.read_text()
        if "<w:pgSz" in xml:
            xml = re.sub(r"<w:pgSz[^>]*/>", '<w:pgSz w:w="11906" w:h="16838"/>', xml)
        else:
            xml = xml.replace("<w:sectPr>", '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>')
        orcid_paragraph = re.compile(
            rf"<w:p>(?P<properties><w:pPr>.*?</w:pPr>)(?P<content>(?:(?!</w:p>).)*ORCID: {re.escape(ORCID_ID)}(?:(?!</w:p>).)*)</w:p>"
        )
        xml, orcid_replacements = orcid_paragraph.subn(
            lambda match: (
                f'<w:p>{match.group("properties")}<w:hyperlink r:id="rIdArchGuardOrcid" w:history="1">'
                f"{match.group('content')}</w:hyperlink></w:p>"
            ),
            xml,
            count=1,
        )
        if orcid_replacements != 1:
            raise ValueError("unable to create the ORCID hyperlink")
        header_ref = '<w:headerReference w:type="default" r:id="rIdArchGuardHeader"/>'
        footer_ref = '<w:footerReference w:type="default" r:id="rIdArchGuardFooter"/>'
        first_footer_ref = '<w:footerReference w:type="first" r:id="rIdArchGuardFirstFooter"/>'
        xml = xml.replace(
            "<w:sectPr>",
            f"<w:sectPr>{header_ref}{footer_ref}{first_footer_ref}<w:titlePg/>",
            1,
        )
        document.write_text(xml)
        header = TITLE_FA if rtl else "ArchGuard-APR — Author manuscript"
        direction = "<w:bidi/>" if rtl else ""
        (unpack / "word/header1.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<w:p><w:pPr><w:jc w:val="center"/>{direction}</w:pPr><w:r><w:rPr><w:sz w:val="16"/></w:rPr><w:t>{html.escape(header)}</w:t></w:r></w:p></w:hdr>'
        )
        (unpack / "word/footer1.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            '<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p></w:ftr>'
        )
        (unpack / "word/footer2.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            '<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p></w:ftr>'
        )
        rels = unpack / "word/_rels/document.xml.rels"
        rel_text = rels.read_text().replace(
            "</Relationships>",
            '<Relationship Id="rIdArchGuardHeader" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>'
            '<Relationship Id="rIdArchGuardFooter" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
            '<Relationship Id="rIdArchGuardFirstFooter" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer2.xml"/>'
            f'<Relationship Id="rIdArchGuardOrcid" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="{ORCID_URL}" TargetMode="External"/>'
            "</Relationships>",
        )
        rels.write_text(rel_text)
        content_types = unpack / "[Content_Types].xml"
        type_text = content_types.read_text().replace(
            "</Types>",
            '<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>'
            '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
            '<Override PartName="/word/footer2.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
            "</Types>",
        )
        content_types.write_text(type_text)
        tmp_docx = path.with_suffix(".tmp.docx")
        with zipfile.ZipFile(tmp_docx, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in sorted(unpack.rglob("*")):
                if item.is_file():
                    archive.write(item, item.relative_to(unpack))
        tmp_docx.replace(path)


def build_docx() -> None:
    DIST.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        temp_dir = Path(temp)
        for language, source, output, rtl in (
            ("English", EN, DIST / "ArchGuard-APR-English.docx", False),
            ("Persian", FA, DIST / "ArchGuard-APR-Persian.docx", True),
        ):
            html_path = temp_dir / f"{language}.html"
            html_path.write_text(_markdown_html(source, rtl=rtl))
            subprocess.run(
                [
                    "textutil",
                    "-convert",
                    "docx",
                    "-output",
                    str(output),
                    "-title",
                    TITLE_FA if rtl else TITLE_EN,
                    "-author",
                    AUTHOR_FA if rtl else AUTHOR_EN,
                    "-subject",
                    SUBJECT,
                    str(html_path),
                ],
                check=True,
            )
            _patch_docx(output, rtl=rtl)


def build_pdf() -> None:
    for stem in ("English", "Persian"):
        source = (DIST / f"ArchGuard-APR-{stem}.docx").resolve()
        output = (DIST / f"ArchGuard-APR-{stem}.pdf").resolve()
        if not source.is_file():
            raise ValueError(f"build DOCX before PDF: {source}")
        script = (
            'tell application "Microsoft Word"\n'
            f'open POSIX file "{source}"\n'
            f'save as active document file name "{output}" file format format PDF\n'
            "close active document saving no\nend tell\n"
        )
        subprocess.run(["osascript", "-e", script], check=True)


def _pdf_pages(path: Path) -> int:
    result = subprocess.run(["pdfinfo", str(path)], check=True, capture_output=True, text=True)
    match = re.search(r"^Pages:\s+(\d+)$", result.stdout, flags=re.MULTILINE)
    if not match:
        raise ValueError(f"unreadable PDF page count: {path}")
    return int(match.group(1))


def finalize(stats: dict[str, int]) -> None:
    outputs = [
        DIST / "ArchGuard-APR-English.docx",
        DIST / "ArchGuard-APR-English.pdf",
        DIST / "ArchGuard-APR-Persian.docx",
        DIST / "ArchGuard-APR-Persian.pdf",
    ]
    for path in outputs:
        if not path.is_file() or path.stat().st_size < 1024:
            raise ValueError(f"missing, empty, or unreadable output: {path}")
    pages = {path.name: _pdf_pages(path) for path in outputs if path.suffix == ".pdf"}
    pages["ArchGuard-APR-English.docx"] = pages["ArchGuard-APR-English.pdf"]
    pages["ArchGuard-APR-Persian.docx"] = pages["ArchGuard-APR-Persian.pdf"]
    manifest = {
        "schema": "archguard.publication-documents/v1",
        "status": "Author manuscript — not peer reviewed",
        "author": AUTHOR_EN,
        "sources": {path.name: _sha(path) for path in (EN, FA, REFS)},
        "outputs": {
            path.name: {
                "sha256": _sha(path),
                "bytes": path.stat().st_size,
                "pages": pages.get(path.name),
            }
            for path in outputs
        },
        "fonts": {
            "english": "Times New Roman",
            "persian": "Arial",
            "persian_selection_reason": "Arial fallback: Vazirmatn, Noto Naskh Arabic, and Noto Sans Arabic were not installed; no font was downloaded.",
        },
        "build_notes": "DOCX created by macOS textutil and normalized OOXML; PDF exported by Microsoft Word. Persian layout uses RTL paragraph direction and the trusted installed Arial fallback. PDF byte identity is not claimed because the exporter may embed variable metadata.",
        "validation": stats,
        "phase13_modified": False,
        "provider_calls": 0,
    }
    (DIST / "document-build-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    checksums = "".join(f"{_sha(path)}  {path.name}\n" for path in outputs)
    (DIST / "SHA256SUMS").write_text(checksums)
    (DIST / "README.md").write_text(
        "# Final bilingual author manuscript\n\n"
        "These English and Persian Word/PDF editions are author manuscripts and have not been peer reviewed. "
        "Build with `python paper/scripts/build_publication_documents.py --format docx`, then `--format pdf`, then `--format finalize`. "
        "The build validates the frozen facts, 23 verified references, resolved citations, figures, placeholders, and output readability. "
        "PDF byte identity is not claimed because Microsoft Word may embed variable metadata.\n"
    )


def write_persian_tex() -> None:
    fa = FA.read_text()
    escaped = fa.replace("\\", r"\textbackslash{}")
    escaped = escaped.replace("&", r"\&").replace("%", r"\%").replace("#", r"\#")
    escaped = re.sub(r"^# (.+)$", r"\\title{\1}", escaped, flags=re.MULTILINE)
    escaped = re.sub(r"^## (.+)$", r"\\section{\1}", escaped, flags=re.MULTILINE)
    escaped = re.sub(r"^### (.+)$", r"\\subsection{\1}", escaped, flags=re.MULTILINE)
    content = (
        "\\documentclass[11pt,a4paper]{article}\n\\usepackage{xepersian}\n"
        "\\settextfont{Arial}\\setlatintextfont{Times New Roman}\n"
        f"\\author{{{AUTHOR_FA}}}\\date{{}}\n\\begin{{document}}\n"
        + escaped
        + "\n\\end{document}\n"
    )
    (MANUSCRIPT / "archguard-apr-fa.tex").write_text(content)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--format", choices=("validate", "docx", "pdf", "finalize"), default="validate"
    )
    args = parser.parse_args()
    stats = validate()
    write_persian_tex()
    if args.format == "docx":
        build_docx()
    elif args.format == "pdf":
        build_pdf()
    elif args.format == "finalize":
        finalize(stats)
    print(json.dumps({"status": "PASS", **stats}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
