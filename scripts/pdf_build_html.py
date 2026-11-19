"""제출 문서 md → 인쇄용 HTML (PDF는 scripts/pdf_render.js가 Playwright로 만든다).

보통은 scripts/make_pdfs.sh로 실행한다. 직접 실행 (프로그램 폴더에서):
    uv run python scripts/pdf_build_html.py <HTML 폴더> <본문 글꼴 Regular 경로> > jobs.json

- md 원본은 바꾸지 않는다
- 다른 제출 문서로 가는 링크·코드 표기는 PDF 파일 이름으로 바꾼다 (예: "02_설치안내.pdf 3-1절")
- 글꼴: 제목·굵은 글씨는 저장소의 Noto Sans KR Bold, 본문은 Regular (저장소에 없음, make_pdfs.sh가 받아 옴)
"""

import html
import json
import sys
from pathlib import Path
from urllib.parse import unquote

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parent.parent
FONT_BOLD = ROOT / "assets" / "fonts" / "NotoSansKR-Bold.otf"

# (원본 md, PDF 이름, 문서 제목). 프롬프트 문서·결과 설명자료가 생기면 여기에 한 줄 추가
DOCS = [
    ("README.md", "01_README.pdf", "README"),
    ("docs/submission/install.md", "02_설치안내.pdf", "설치·실행 안내"),
    ("docs/submission/manual.md", "03_사용매뉴얼.pdf", "사용 매뉴얼"),
    ("docs/submission/troubleshooting.md", "04_오류와제약.pdf", "오류와 제약"),
    ("docs/submission/data-spec.md", "05_데이터활용명세.pdf", "데이터 활용 명세"),
    ("docs/submission/prompts-models.md", "06_프롬프트와모델.pdf", "프롬프트·모델"),
    ("docs/submission/results.md", "07_결과설명자료.pdf", "결과 설명자료"),
]
PDF_BY_NAME = {Path(src).name: pdf for src, pdf, _ in DOCS}


def pdf_name(target: str) -> str | None:
    """링크·코드 표기가 제출 문서를 가리키면 그 PDF 이름."""
    path = target.split("#")[0].strip()
    if not path or "://" in path:
        return None
    name = Path(path).name
    if name == "README.md" and path not in ("README.md", "../../README.md"):
        return None  # 다른 폴더의 README (assets/fonts 등)
    return PDF_BY_NAME.get(name)


def rewrite(tokens, base: Path) -> None:
    """제출 문서 링크는 PDF 이름 글자로 바꾼다 (PDF 안의 상대 링크는 열리지 않으므로 글자로만).

    이미지는 HTML을 다른 폴더에 만들므로 원본 md 기준 절대 경로(file://)로 바꾼다.
    """
    for tok in tokens:
        if tok.type != "inline" or not tok.children:
            continue
        out, i, kids = [], 0, tok.children
        while i < len(kids):
            k = kids[i]
            src = k.attrGet("src") if k.type == "image" else None
            if src and "://" not in src:
                # markdown-it이 한글 파일 이름을 %인코딩해 두므로 풀어서 경로로 만든다
                k.attrSet("src", (base / unquote(src)).resolve().as_uri())
            if k.type == "code_inline" and (pdf := pdf_name(k.content)):
                k.content = pdf
            if k.type == "link_open" and (pdf := pdf_name(k.attrGet("href") or "")):
                j = i + 1
                while kids[j].type != "link_close":
                    j += 1
                inner = kids[i + 1 : j]
                text = "".join(c.content for c in inner if c.type in ("text", "code_inline"))
                t = type(k)("text", "", 0)
                # 링크 글자가 파일 이름이면 PDF 이름으로, 아니면 "글자(PDF 이름)"
                t.content = pdf if pdf_name(text) or text.endswith(".md") else f"{text}({pdf})"
                out.append(t)
                i = j + 1
                continue
            out.append(k)
            i += 1
        tok.children = out


CSS = """
@font-face { font-family: KR; src: url('%(regular)s'); font-weight: 400; }
@font-face { font-family: KR; src: url('%(bold)s'); font-weight: 700; }
@page { size: A4; margin: 16mm 14mm 18mm 14mm; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: KR, sans-serif; font-size: 10pt; line-height: 1.6; color: #1f2328; background: #fff;
       word-break: keep-all; overflow-wrap: anywhere; }
h1, h2, h3, h4 { font-weight: 700; line-height: 1.35; break-after: avoid; page-break-after: avoid; }
h1 { font-size: 19pt; border-bottom: 2px solid #1f6f5c; padding-bottom: 6px; margin: 0 0 14px; }
h2 { font-size: 14pt; border-bottom: 1px solid #d0d7de; padding-bottom: 4px; margin: 22px 0 10px; }
h3 { font-size: 11.5pt; margin: 16px 0 8px; }
h4 { font-size: 10.5pt; margin: 12px 0 6px; }
p, ul, ol { margin: 6px 0; }
li { margin: 2px 0; }
strong { font-weight: 700; }
p:has(> strong:only-child) { break-after: avoid; page-break-after: avoid; }
a { color: #0b5cad; text-decoration: none; }
code { font-family: Menlo, Consolas, KR, monospace; font-size: 8.6pt; background: #f2f4f6;
       padding: 1px 4px; border-radius: 3px; }
pre { background: #f6f8fa; border: 1px solid #d8dee4; border-radius: 5px; padding: 8px 10px;
      white-space: pre-wrap; overflow-wrap: anywhere; break-inside: avoid; }
pre code { background: none; padding: 0; font-size: 8.3pt; }
table { border-collapse: collapse; width: 100%%; margin: 8px 0 12px; font-size: 8.4pt; line-height: 1.45; }
thead { display: table-header-group; }
tr { break-inside: avoid; page-break-inside: avoid; }
th, td { border: 1px solid #c9d1d9; padding: 4px 6px; vertical-align: top; text-align: left;
         overflow-wrap: anywhere; word-break: break-word; }
th { background: #eef3f1; font-weight: 700; }
td code, th code { font-size: 7.8pt; padding: 0 2px; }
blockquote { margin: 8px 0; padding: 4px 10px; border-left: 3px solid #1f6f5c; color: #444;
             background: #f7faf9; }
img { display: block; max-width: 100%%; max-height: 225mm; margin: 10px auto 4px; border: 1px solid #d8dee4;
      border-radius: 6px; break-inside: avoid; }
p:has(> img) { break-inside: avoid; break-after: avoid; margin: 8px 0 0; }
p:has(> img) + p > em:only-child { display: block; }
em { font-style: normal; color: #57606a; font-size: 9pt; }
hr { border: 0; border-top: 1px solid #d0d7de; margin: 16px 0; }
"""


def build(out_dir: Path, font_regular: Path) -> list[dict]:
    md = MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])
    css = CSS % {"regular": font_regular.resolve().as_uri(), "bold": FONT_BOLD.as_uri()}
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs = []
    for src, pdf, title in DOCS:
        tokens = md.parse((ROOT / src).read_text(encoding="utf-8"))
        rewrite(tokens, (ROOT / src).parent)
        body = md.renderer.render(tokens, md.options, {})
        page = (
            f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            f"<title>{html.escape(title)}</title><style>{css}</style></head>"
            f"<body>{body}</body></html>"
        )
        path = (out_dir / (Path(pdf).stem + ".html")).resolve()
        path.write_text(page, encoding="utf-8")
        jobs.append({"html": str(path), "pdf": pdf, "title": title})
    return jobs


if __name__ == "__main__":
    print(json.dumps(build(Path(sys.argv[1]), Path(sys.argv[2])), ensure_ascii=False))
