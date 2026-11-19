"""저장된 Markdown을 편집 가능한 Word/HWPX 문서로 내보낸다."""

from io import BytesIO

from markdown_it import MarkdownIt


def _plain(value):
    return (value.replace("⚠️", "주의:").replace("✅", "통과:")
            .replace("❌", "실패:").replace("🧪", "가상 데이터:"))


def blocks(markdown):
    tokens = MarkdownIt("commonmark").enable("table").parse(markdown)
    result, lists = [], []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.type in {"bullet_list_open", "ordered_list_open"}:
            lists.append(token.type)
        elif token.type in {"bullet_list_close", "ordered_list_close"}:
            lists.pop()
        elif token.type == "table_open":
            rows, row = [], []
            i += 1
            while tokens[i].type != "table_close":
                part = tokens[i]
                if part.type == "tr_open":
                    row = []
                elif part.type == "inline":
                    row.append(part.children or [])
                elif part.type == "tr_close":
                    rows.append(row)
                i += 1
            result.append(("table", rows))
        elif token.type in {"heading_open", "paragraph_open"}:
            kind = token.tag if token.type == "heading_open" else "bullet" if lists else "p"
            result.append((kind, tokens[i + 1].children or []))
        elif token.type == "fence":
            result.append(("p", [{"text": token.content}]))
        i += 1
    return result


def runs(tokens):
    bold = italic = False
    result = []
    for token in tokens:
        if isinstance(token, dict):
            result.append((_plain(token["text"]), False, False))
        elif token.type == "strong_open":
            bold = True
        elif token.type == "strong_close":
            bold = False
        elif token.type == "em_open":
            italic = True
        elif token.type == "em_close":
            italic = False
        elif token.type in {"softbreak", "hardbreak"}:
            result.append(("\n", bold, italic))
        elif token.type in {"text", "code_inline", "html_inline", "image"}:
            result.append((_plain(token.content), bold, italic))
    return result


def to_docx(markdown: str) -> bytes:
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin = section.bottom_margin = Cm(2)
    section.left_margin = section.right_margin = Cm(2)
    for name, size in [("Normal", 10.5), ("Title", 20), ("Heading 1", 15),
                       ("Heading 2", 12), ("Heading 3", 11)]:
        style = doc.styles[name]
        style.font.name = "맑은 고딕"
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor.from_string("161616")
        style.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Apple SD Gothic Neo")
        for border in list(style.element.xpath("./w:pPr/w:pBdr")):
            border.getparent().remove(border)
        style.paragraph_format.space_after = Pt(6)
        style.paragraph_format.line_spacing = 1.4

    def write(paragraph, tokens, *, header=False, table=False):
        for text, bold, italic in runs(tokens):
            run = paragraph.add_run(text)
            run.bold, run.italic = bold or header, italic
            if table:
                run.font.size = Pt(9)
        if table:
            paragraph.paragraph_format.space_after = Pt(3)
            paragraph.paragraph_format.line_spacing = 1.25

    for kind, content in blocks(markdown):
        if kind == "table":
            count = max(map(len, content), default=0)
            if not count:
                continue
            table = doc.add_table(rows=len(content), cols=count)
            table.style = "Table Grid"
            table.autofit = False
            widths = ([4, 13] if count == 2 else [6, 2.5, 8.5] if count == 3
                      else [17 / count] * count)
            for column, width in zip(table.columns, widths, strict=True):
                column.width = Cm(width)
            for r, row in enumerate(content):
                if r == 0:
                    repeat = OxmlElement("w:tblHeader")
                    table.rows[r]._tr.get_or_add_trPr().append(repeat)
                for c, text in enumerate(row):
                    cell = table.cell(r, c)
                    cell.width = Cm(widths[c])
                    write(cell.paragraphs[0], text, header=r == 0, table=True)
                    if r == 0:
                        fill = OxmlElement("w:shd")
                        fill.set(qn("w:fill"), "F3F3F0")
                        cell._tc.get_or_add_tcPr().append(fill)
            doc.add_paragraph().paragraph_format.space_after = Pt(2)
        else:
            if kind == "h1":
                p = doc.add_paragraph(style="Title")
            elif kind.startswith("h"):
                p = doc.add_paragraph(style=f"Heading {min(int(kind[1:]) - 1, 3)}")
            else:
                p = doc.add_paragraph(style="List Bullet" if kind == "bullet" else "Normal")
            write(p, content)
    output = BytesIO()
    doc.save(output)
    return output.getvalue()


def to_hwpx(markdown: str) -> bytes:
    from hwpx import HwpxDocument

    doc = HwpxDocument.new()
    doc.set_page_setup(paper_size="A4", margin_left_mm=20, margin_right_mm=20,
                       margin_top_mm=20, margin_bottom_mm=20)
    body = doc.styles.ensure_run(font="맑은 고딕", size=10.5)
    for kind, content in blocks(markdown):
        if kind == "table":
            count = max(map(len, content), default=0)
            if not count:
                continue
            table = doc.add_table(len(content), count, width=48189, char_pr_id_ref=body)
            for r, row in enumerate(content):
                for c, tokens in enumerate(row):
                    table.set_cell_text(r, c, "".join(text for text, _, _ in runs(tokens)))
            doc.add_paragraph("")
        else:
            heading = kind.startswith("h")
            size = 20 if kind == "h1" else 15 if kind == "h2" else 12 if heading else 10.5
            p = doc.add_paragraph(include_run=False)
            if kind == "bullet":
                p.add_run("• ", font="맑은 고딕", size=size)
            for text, bold, italic in runs(content):
                p.add_run(text, font="맑은 고딕", size=size, bold=bold or heading, italic=italic)
    return doc.to_bytes()
