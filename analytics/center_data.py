"""센터 지정 데이터(data/raw/) 읽기 공통 규칙.

실데이터 형식이 명세서와 조금 달라도 앱이 멈추지 않게 한다.
- 글자 인코딩: UTF-8(BOM 포함) → CP949(엑셀 기본) 순서로 읽는다
- 날짜: 2025-05-12, 2025.05.12, 2025/05/12도 20250512로 바꿔 읽는다
- 그래도 읽지 못하면(열 이름이 다름, 빈 파일 등) 부르는 쪽이 가상 데이터로 대신하고,
  화면에 "센터 데이터를 읽지 못해 가상 데이터로 확인했어요(이유: …)"를 띄운다
"""

import re
from pathlib import Path

import pandas as pd

ENCODINGS = ("utf-8-sig", "cp949")
FALLBACK_NOTICE = "센터 데이터를 읽지 못해 가상 데이터로 확인했어요"
_DASHED_DATE = re.compile(r"^(\d{4})[-./](\d{1,2})[-./](\d{1,2})$")


def read_csv_any(path: Path, **kwargs) -> pd.DataFrame:
    """UTF-8(BOM 포함), CP949 순서로 읽는다. 둘 다 안 되면 마지막 오류를 그대로 던진다."""
    error: Exception | None = None
    for encoding in ENCODINGS:
        try:
            return pd.read_csv(path, encoding=encoding, **kwargs)
        except UnicodeDecodeError as exc:
            error = exc
    raise error  # type: ignore[misc]


def normalize_dates(df: pd.DataFrame, column: str = "base_date") -> pd.DataFrame:
    """2025-05-12 같은 날짜를 명세서 형식 20250512로 바꾼다 (이미 YYYYMMDD면 그대로)."""
    if column not in df:
        return df
    text = df[column].astype(str).str.strip()
    parts = text.str.extract(_DASHED_DATE)
    dashed = parts[0].notna()
    if dashed.any():
        df = df.copy()
        df.loc[dashed, column] = parts[0] + parts[1].str.zfill(2) + parts[2].str.zfill(2)
    return df


def require_columns(df: pd.DataFrame, columns, name: str) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"{name} 파일에 필수 열 {', '.join(missing)}이(가) 없어요")


def reason_text(exc: Exception, name: str) -> str:
    """읽기 실패 이유를 쉬운 말로 (화면 안내에 쓴다)."""
    if isinstance(exc, pd.errors.EmptyDataError):
        return f"{name} 파일이 비어 있어요"
    if isinstance(exc, UnicodeDecodeError):
        return f"{name} 파일의 글자 인코딩을 알 수 없어요 (UTF-8 또는 CP949로 저장해 주세요)"
    if isinstance(exc, KeyError):
        return f"{name} 파일에 필수 열 {exc.args[0]}이(가) 없어요"
    if isinstance(exc, ValueError) and "필수 열" in str(exc):
        return str(exc)
    return f"{name} 파일을 읽지 못했어요 ({type(exc).__name__})"


def fallback_notice(reason: str) -> str:
    return f"{FALLBACK_NOTICE}(이유: {reason})"
