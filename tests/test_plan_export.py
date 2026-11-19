from io import BytesIO
from zipfile import ZipFile

from docx import Document
from lxml import etree

from app.plan_export import to_docx, to_hwpx

SOURCE = """# 수정한 감귤 축제 기획서

## 1. 사업 개요

| 항목 | 내용 |
| --- | --- |
| 축제명 | 수정한 감귤 축제 |
| 장소 | 사용자가 확인한 장소 |

## 2. 프로그램

- **가족 체험**: 감귤을 활용해요.
- 미확인 사항을 확인해요.

> 가상 데이터는 참고로만 사용해요.
"""


def test_docx_preserves_edited_korean_text_tables_and_emphasis():
    doc = Document(BytesIO(to_docx(SOURCE)))
    paragraphs = "\n".join(p.text for p in doc.paragraphs)
    assert "수정한 감귤 축제 기획서" in paragraphs
    assert "가족 체험" in paragraphs and "가상 데이터는 참고" in paragraphs
    assert doc.tables[0].cell(2, 1).text == "사용자가 확인한 장소"
    assert len(doc.tables[0].rows) == 3
    assert any(r.bold and r.text == "가족 체험" for p in doc.paragraphs for r in p.runs)


def test_hwpx_is_valid_package_with_edited_text_and_real_table():
    from hwpx import HwpxDocument

    data = to_hwpx(SOURCE)
    with ZipFile(BytesIO(data)) as archive:
        assert archive.testzip() is None
        assert archive.read("mimetype") == b"application/hwp+zip"
        for name in archive.namelist():
            if name.endswith(".xml"):
                etree.fromstring(archive.read(name))
        section = etree.fromstring(archive.read("Contents/section0.xml"))
        text = "".join(section.itertext())
        assert all(value in text for value in ("수정한 감귤 축제", "사용자가 확인한 장소", "가족 체험"))
        assert len(section.findall(".//{*}tbl")) == 1
    reopened = HwpxDocument.open(BytesIO(data))
    assert len(reopened.sections) == 1
