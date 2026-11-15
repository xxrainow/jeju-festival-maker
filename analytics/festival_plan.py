"""문체부 「2026년 지역축제 개최 계획 현황(공개용)」 로더와 품질 표시.

- "조사표" 시트, 헤더 3줄(5~7행), 자료는 9행부터
- 담당자 칸(소속, 부서명, 직급/직책, 성명, 연락처)은 읽지 않는다. 결과 파일에도 남지 않는다
- "미집계", "최초 개최", "모름", "미확정" 같은 글자는 결측으로 바꾸고 원래 글자를 `*_missing`에 남긴다
- 방문객 계측 방법(계측/추정/미집계/기타/무응답)은 그대로 두고, 1인당 비용은 "계측"만 계산한다
- "추정"이면서 계측 방법 비고가 통신 데이터인 축제는 `per_capita_telecom_krw`에 따로 계산한다 (기본값에 섞지 않음)
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd

PLAN_PATH = Path("data/raw/2026년 지역축제 개최 계획 현황(공개용).xlsx")
SHEET = "조사표"
HEADER_ROWS = 8  # 1~8행 (제목, 헤더 3줄, "지역" 구분 행)

# 엑셀 열 위치(0부터) → 이름. 담당자 칸(34~38)은 여기에 없어서 읽지 않는다
COLUMNS = {
    1: "no",
    2: "sido",  # 광역자치단체명 (예: "17. 제주")
    3: "sigungu",  # 기초자치단체명 ("-"이면 광역 주최)
    4: "name",
    5: "festival_type",
    6: "place_name",
    7: "place_type",
    8: "place_sido",
    9: "place_sigungu",
    10: "place_emd",
    11: "start_year",
    12: "start_month",
    13: "start_day",
    14: "end_year",
    15: "end_month",
    16: "end_day",
    17: "days",
    18: "period_note",
    19: "cycle",
    20: "first_year",
    21: "budget_total",  # 예산 합계 (백만원)
    22: "budget_national",
    23: "budget_local",
    24: "budget_other",
    25: "national_ministry",
    26: "visitors",  # 방문객수(전년) 전체
    27: "visitors_domestic",
    28: "visitors_foreign",
    29: "visitor_method",  # 계측 방법
    30: "visitor_method_note",  # 계측 방법 비고 (예: 통신 데이터, 주차면수)
    31: "org_name",
    32: "org_type",
    33: "org_basis",
    39: "note",
}
# 형식이 바뀌었는지 확인할 헤더 (열 위치, 5~7행 중 한 줄의 글자)
EXPECTED_HEADERS = {
    4: "축제명",
    21: "합계",
    26: "전체",
    29: "계측 방법",
    34: "담당자",
    37: "성명",
    38: "연락처",
}
PERSONAL_COLUMNS = [34, 35, 36, 37, 38]  # 담당자 소속, 부서명, 직급/직책, 성명, 연락처
PERSONAL_NAMES = ["소속", "부서명", "직급", "직책", "성명", "연락처", "담당자"]
NUMERIC_COLUMNS = [
    "days",
    "first_year",
    "budget_total",
    "budget_national",
    "budget_local",
    "budget_other",
    "visitors",
    "visitors_domestic",
    "visitors_foreign",
]
CODED_COLUMNS = ["sido", "festival_type", "place_type", "place_sido", "cycle", "visitor_method"]
_CODE = re.compile(r"^\s*(\d+)\.\s*(.+?)\s*$")
# 구분자가 있는 번호(064-710-1234) 또는 구분자 없는 휴대전화(01012345678). 소수 숫자와 헷갈리지 않게 앞뒤 숫자·점 제외
_PHONE = re.compile(r"(?<![\d.])(?:0\d{1,2}[-)\s]\d{3,4}[-\s]\d{4}|01[016789]\d{7,8})(?![\d.])")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")

# 축제별 메모 (광역, 축제명) → 메모. 수치는 바꾸지 않고 해석할 때 주의할 점만 남긴다
FESTIVAL_MEMOS = {
    ("제주", "제19회 전농로 왕벚꽃 축제"): "거리형 행사라 통행 인원이 포함됐을 수 있음",
}

MEASURED = "계측"
ESTIMATED = "추정"
UNDECIDED_PLACE = "미정"


def _check_headers(path: Path) -> None:
    header = pd.read_excel(path, sheet_name=SHEET, header=None, skiprows=4, nrows=3)
    for col, text in EXPECTED_HEADERS.items():
        cells = " ".join(str(v) for v in header[col].dropna())
        if text not in cells.replace("\n", " "):
            raise ValueError(
                f"조사표 {col + 1}번째 열 헤더가 예상('{text}')과 달라요. 파일 형식을 확인해 주세요"
            )


def split_code(value) -> tuple[str | None, str | None]:
    """ "01. 문화예술" → ("01", "문화예술"). 형식이 아니면 (None, 원래 글자)."""
    if not isinstance(value, str):
        return None, None
    m = _CODE.match(value)
    return (m.group(1), m.group(2)) if m else (None, value.strip())


def to_number(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """숫자가 아닌 글자는 결측으로 바꾸고 그 글자를 사유로 돌려준다. (숫자, 결측 사유)."""
    numbers = pd.to_numeric(series, errors="coerce")
    reason = series.where(numbers.isna() & series.notna()).astype("string").str.strip()
    return numbers, reason


def assert_no_personal_info(df: pd.DataFrame) -> None:
    """담당자 칸 이름이나 전화번호·이메일 같은 글자가 있으면 저장하지 않게 멈춘다."""
    bad_cols = [c for c in df.columns if any(n in str(c) for n in PERSONAL_NAMES)]
    if bad_cols:
        raise ValueError(f"개인정보 칸이 남아 있어요: {', '.join(bad_cols)}")
    for col in df.select_dtypes(include=["object", "string"]).columns:
        text = df[col].dropna().astype(str)
        hit = text[text.str.contains(_PHONE) | text.str.contains(_EMAIL)]
        if not hit.empty:
            raise ValueError(f"{col} 칸에 전화번호나 이메일처럼 보이는 값이 {len(hit)}건 있어요")


def load_festival_plan(path: Path = PLAN_PATH) -> pd.DataFrame:
    _check_headers(path)
    raw = pd.read_excel(
        path,
        sheet_name=SHEET,
        header=None,
        skiprows=HEADER_ROWS,
        usecols=list(COLUMNS),
        dtype=object,
    )
    df = raw.rename(columns=COLUMNS)
    df = df[df["no"].notna()].reset_index(drop=True)

    for col in CODED_COLUMNS:
        codes = df[col].map(split_code)
        df[f"{col}_code"] = codes.str[0]
        df[col] = codes.str[1]
    for col in [
        "sigungu",
        "name",
        "place_name",
        "place_sigungu",
        "place_emd",
        "visitor_method_note",
    ]:
        df[col] = df[col].astype("string").str.strip()
    for col in NUMERIC_COLUMNS:
        df[col], reason = to_number(df[col])
        if reason.notna().any():
            df[f"{col}_missing"] = reason
    for part in ["start", "end"]:
        ymd = df[[f"{part}_year", f"{part}_month", f"{part}_day"]].apply(
            pd.to_numeric, errors="coerce"
        )
        df[f"{part}_date"] = pd.to_datetime(
            {"year": ymd.iloc[:, 0], "month": ymd.iloc[:, 1], "day": ymd.iloc[:, 2]},
            errors="coerce",
        )
    # 총일수가 비어 있으면 시작일·종료일로 계산 (날짜도 미정이면 그대로 결측)
    computed = (df["end_date"] - df["start_date"]).dt.days + 1
    df["days_source"] = np.where(
        df["days"].notna(), "조사표", np.where(computed.notna(), "날짜 계산", None)
    )
    df["days"] = df["days"].fillna(computed)
    df["duration_class"] = (
        pd.cut(df["days"], bins=[0, 1, 3, np.inf], labels=["1일", "2~3일", "4일 이상"])
        .astype("string")
        .fillna("미정")
    )
    df["local_gov"] = df["sigungu"].where(df["sigungu"].ne("-"), df["place_sigungu"])
    for part in ["start", "end"]:
        for unit in ["year", "month", "day"]:
            col = f"{part}_{unit}"
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    text = df.select_dtypes(include="object").columns
    df[text] = df[text].astype("string")
    return add_quality_flags(df)


def iqr_bounds(values: pd.Series) -> tuple[float, float]:
    """1인당 비용은 오른쪽으로 크게 치우쳐 원 단위 IQR 하한이 음수가 된다. log10에서 IQR 1.5배를 쓴다."""
    logs = np.log10(values[values > 0])
    q1, q3 = logs.quantile([0.25, 0.75])
    return 10 ** (q1 - 1.5 * (q3 - q1)), 10 ** (q3 + 1.5 * (q3 - q1))


def add_quality_flags(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    measured = df["visitor_method"].eq(MEASURED) & df["visitors"].gt(0) & df["budget_total"].notna()
    df["per_capita_krw"] = (df["budget_total"] * 1_000_000 / df["visitors"]).where(measured)
    df["telecom_estimate"] = df["visitor_method"].eq(ESTIMATED) & df["visitor_method_note"].fillna(
        ""
    ).str.contains("통신")
    telecom = df["telecom_estimate"] & df["visitors"].gt(0) & df["budget_total"].notna()
    df["per_capita_telecom_krw"] = (df["budget_total"] * 1_000_000 / df["visitors"]).where(telecom)
    df["memo"] = [FESTIVAL_MEMOS.get((sido, name)) for sido, name in zip(df["sido"], df["name"])]

    reasons = pd.DataFrame(index=df.index)
    has_visitors = df["visitors"].notna()
    reasons["같은 기초자치단체에 같은 방문객 수"] = has_visitors & df.duplicated(
        ["sido", "local_gov", "visitors"], keep=False
    )
    reasons["소수점 방문객 수"] = has_visitors & (df["visitors"] % 1 != 0)
    reasons["예산 0원"] = df["budget_total"].eq(0)
    low, high = iqr_bounds(df["per_capita_krw"].dropna())
    reasons["1인당 비용 극단값(낮음)"] = df["per_capita_krw"] < low
    reasons["1인당 비용 극단값(높음)"] = df["per_capita_krw"] > high
    df["per_capita_outlier"] = (
        reasons["1인당 비용 극단값(낮음)"] | reasons["1인당 비용 극단값(높음)"]
    )
    df["suspect_reasons"] = reasons.apply(
        lambda r: ", ".join(r.index[r]) if r.any() else None, axis=1
    )
    df.attrs["per_capita_bounds"] = (low, high)
    return df
