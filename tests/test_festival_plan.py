import pandas as pd
import pytest

from analytics.festival_plan import (
    assert_no_personal_info,
    iqr_bounds,
    load_festival_plan,
    split_code,
)

WIDTH = 40


def header_rows() -> list[list]:
    rows = [[None] * WIDTH for _ in range(8)]
    rows[1][1] = "2026년 연간 지역축제 개최 계획"
    h5, h6, h7 = rows[4], rows[5], rows[6]
    h5[1:7] = ["연번", "광역자치단체명", "기초자치단체명", "축제명", "축제 유형", "개최 장소"]
    h5[11], h5[21], h5[26], h5[34], h5[39] = (
        "개최기간",
        "예산(백만원)",
        "방문객수(前년)",
        "담당자",
        "비고",
    )
    h6[6], h6[7], h6[11], h6[14], h6[17] = "장소명", "축제 유형", "시작일", "종료일", "총\n일수"
    h6[21], h6[26], h6[29] = "합계", "전체", "계측 방법"
    h6[34:39] = ["소속", "부서명", "직급/직책", "성명", "연락처"]
    h7[8:17] = ["시도", "시군구", "읍면동", "년", "월", "일", "년", "월", "일"]
    rows[7][2] = "지역"
    return rows


def festival(no, **kw) -> list:
    r = [None] * WIDTH
    r[1], r[2], r[3], r[4] = no, kw.get("sido", "17. 제주"), kw.get("sigungu", "-"), f"축제{no}"
    r[5], r[6], r[7] = (
        kw.get("ftype", "01. 문화예술"),
        kw.get("place", "새별오름"),
        kw.get("ptype", "02. 녹지형"),
    )
    r[8], r[9], r[10] = "17. 제주", kw.get("city", "제주시"), kw.get("emd", "애월읍")
    r[11:17] = kw.get("dates", [2026, 3, 1, 2026, 3, 2])
    r[17] = kw.get("days", 2)
    r[19], r[20] = "01. 매년", kw.get("first", 2010)
    r[21] = kw.get("budget", 100)
    r[26] = kw.get("visitors", 10000)
    r[27], r[28] = kw.get("domestic", 9000), kw.get("foreign", "모름")
    r[29], r[30] = kw.get("method", "01. 계측"), kw.get("note", "유인")
    # 담당자 칸: 읽히면 안 되는 가짜 값
    r[34:39] = ["제주시", "관광과", "주무관", "홍길동", "064-710-1234"]
    return r


def write_plan(tmp_path, rows) -> str:
    path = tmp_path / "plan.xlsx"
    pd.DataFrame(header_rows() + rows).to_excel(
        path, sheet_name="조사표", header=False, index=False
    )
    return path


def test_personal_columns_are_never_loaded(tmp_path):
    df = load_festival_plan(write_plan(tmp_path, [festival(1)]))
    assert_no_personal_info(df)
    text = df.astype(str).to_string()
    assert "홍길동" not in text and "064-710-1234" not in text and "주무관" not in text


def test_missing_words_become_na_with_reason(tmp_path):
    rows = [
        festival(1, budget="미확정", visitors="최초 개최", first="미상"),
        festival(2, visitors="미집계", domestic="미집계"),
    ]
    df = load_festival_plan(write_plan(tmp_path, rows))
    assert df["budget_total"].isna().iloc[0]
    assert df["budget_total_missing"].iloc[0] == "미확정"
    assert df["visitors_missing"].tolist() == ["최초 개최", "미집계"]
    assert df["first_year_missing"].iloc[0] == "미상"
    assert df["visitors_foreign"].isna().all()
    assert (df["visitors_foreign_missing"] == "모름").all()


def test_codes_days_and_duration(tmp_path):
    rows = [
        festival(1, days=None, dates=[2026, 5, 1, 2026, 5, 4]),
        festival(2, days=None, dates=[2026, None, None, 2026, None, None]),
        festival(3, days=3),
    ]
    df = load_festival_plan(write_plan(tmp_path, rows))
    assert df["festival_type"].iloc[0] == "문화예술" and df["festival_type_code"].iloc[0] == "01"
    assert df["sido"].iloc[0] == "제주"
    assert df["days"].tolist()[0] == 4 and df["days_source"].iloc[0] == "날짜 계산"
    assert df["duration_class"].tolist() == ["4일 이상", "미정", "2~3일"]


def test_quality_flags(tmp_path):
    rows = [
        festival(1, visitors=3000, city="제주시"),
        festival(2, visitors=3000, city="제주시"),  # 같은 기초자치단체 같은 방문객
        festival(3, visitors=3000, city="서귀포시"),
        festival(4, visitors=1234.5),
        festival(5, budget=0, visitors=5000),
        festival(6, method="02. 추정", note="통신 데이터", visitors=8000),
    ]
    df = load_festival_plan(write_plan(tmp_path, rows)).set_index("name")
    reasons = df["suspect_reasons"].fillna("")
    assert "같은 방문객" in reasons["축제1"] and "같은 방문객" in reasons["축제2"]
    assert "같은 방문객" not in reasons["축제3"]
    assert "소수점" in reasons["축제4"]
    assert "예산 0원" in reasons["축제5"]
    # 1인당 비용은 계측만
    assert df.loc["축제1", "per_capita_krw"] == pytest.approx(100 * 1_000_000 / 3000)
    assert pd.isna(df.loc["축제6", "per_capita_krw"])
    assert df["telecom_estimate"].tolist() == [False] * 5 + [True]


def test_iqr_bounds_on_log_scale():
    low, high = iqr_bounds(pd.Series([1000, 2000, 4000, 8000, 16000]))
    assert low < 1000 and high > 16000
    low, high = iqr_bounds(pd.Series([5000] * 8 + [50, 500000]))
    assert low > 50 and high < 500000


def test_split_code():
    assert split_code("05. 지역특산물") == ("05", "지역특산물")
    assert split_code("미정") == (None, "미정")
    assert split_code(None) == (None, None)


def test_personal_info_guard():
    with pytest.raises(ValueError, match="성명"):
        assert_no_personal_info(pd.DataFrame({"성명": ["가"]}))
    with pytest.raises(ValueError, match="전화번호"):
        assert_no_personal_info(pd.DataFrame({"note": ["문의 010-1234-5678"]}))
    assert_no_personal_info(pd.DataFrame({"note": ["391.083301508", "남조로 2455"]}))


def test_changed_header_is_rejected(tmp_path):
    rows = header_rows()
    rows[5][37] = "이름"
    path = tmp_path / "plan.xlsx"
    pd.DataFrame(rows + [festival(1)]).to_excel(
        path, sheet_name="조사표", header=False, index=False
    )
    with pytest.raises(ValueError, match="헤더"):
        load_festival_plan(path)
