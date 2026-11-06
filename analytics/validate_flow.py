"""4-11 내국인 유동인구(읍면동) CSV 검증.

검사 결과를 통과·경고·오류로 나누고, 비전문가가 읽을 수 있는 한국어 문장으로 돌려준다.
파일을 읽지 못하거나 컬럼이 없어도 예외를 던지지 않고 오류 문장으로 알려준다 (앱이 멈추지 않게).

허용 범위 (명세서끼리 표기가 엇갈리는 부분은 둘 다 허용):
- time: "1"과 "01" 모두 (비고는 "01~24시", 예시값은 "1")
- pt_month: "5"와 "05" 모두
- age: SKT 13개 + 0009(10세 이하) + KT 9개
"""

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pandas as pd

from analytics.flow_spec import (
    AGE_KT,
    AGE_SKT,
    AGE_SKT_UNDER10,
    COLUMNS,
    DISTRICTS,
    EMD_CODES,
    POP_COLUMNS,
    RESIDENCES,
    SEXES,
)

PASS, WARN, ERROR = "통과", "경고", "오류"
Level = Literal["통과", "경고", "오류"]
KEY_COLUMNS = ["base_date", "time", "emd_cd", "sex", "age", "resd"]
ENCODINGS = ["utf-8-sig", "cp949"]
EXAMPLES = 3


@dataclass
class Finding:
    level: Level
    message: str


@dataclass
class ValidationReport:
    findings: list[Finding] = field(default_factory=list)
    row_count: int = 0
    period: tuple[str, str] | None = None  # (YYYY-MM-DD, YYYY-MM-DD)
    regions: list[str] = field(default_factory=list)
    data: pd.DataFrame | None = None  # 오류가 없을 때만: 날짜·시간·인구를 숫자로 바꾼 표

    @property
    def status(self) -> Level:
        levels = {f.level for f in self.findings}
        return ERROR if ERROR in levels else WARN if WARN in levels else PASS

    def add(self, level: Level, message: str) -> None:
        self.findings.append(Finding(level, message))

    def summary(self) -> str:
        head = f"검사 결과: {self.status}"
        if self.period:
            head += f" ({self.row_count:,}행, 기간 {self.period[0]} ~ {self.period[1]}, 행정동 {len(self.regions)}곳)"
        return "\n".join([head, *(f"[{f.level}] {f.message}" for f in self.findings)])


def read_flow_csv(source) -> tuple[pd.DataFrame | None, str | None]:
    """경로, 바이트, 업로드 파일 객체를 모두 받는다. .gz도 읽는다. (표, 오류 문장)."""
    try:
        if isinstance(source, (str, Path)):
            raw = Path(source).read_bytes()
            name = str(source)
        else:
            raw = source if isinstance(source, bytes) else source.read()
            name = getattr(source, "name", "")
    except OSError as exc:
        return None, f"파일을 열지 못했어요 ({exc.strerror or exc}). 파일 경로를 확인해 주세요."
    compression = "gzip" if name.endswith(".gz") or raw[:2] == b"\x1f\x8b" else None
    for encoding in ENCODINGS:
        try:
            df = pd.read_csv(
                io.BytesIO(raw),
                dtype=str,
                keep_default_na=False,
                encoding=encoding,
                compression=compression,
            )
            return df, None
        except UnicodeDecodeError:
            continue
        except pd.errors.EmptyDataError:
            return None, "파일이 비어 있어요."
        except Exception as exc:  # noqa: BLE001 - 형식이 깨진 파일도 앱이 멈추지 않게
            return (
                None,
                f"CSV 형식으로 읽지 못했어요 ({type(exc).__name__}). 쉼표로 구분된 CSV 파일인지 확인해 주세요.",
            )
    return None, "글자 인코딩을 알 수 없어요. UTF-8 또는 CP949(엑셀 기본)로 저장해 주세요."


def _rows(mask: pd.Series) -> str:
    """문제 행의 파일 줄 번호 예시 (머리글이 1번째 줄)."""
    lines = (mask[mask].index[:EXAMPLES] + 2).astype(str).tolist()
    return ", ".join(lines) + (" 등" if mask.sum() > EXAMPLES else "")


def _values(series: pd.Series) -> str:
    vals = series.unique()[:EXAMPLES]
    return ", ".join(f'"{v}"' for v in vals)


def _check_allowed(report, df, col, allowed, label) -> None:
    bad = ~df[col].isin(allowed)
    if bad.any():
        report.add(
            ERROR,
            f"{label}({col}) 값 중 허용되지 않은 값이 {bad.sum():,}행 있어요: {_values(df.loc[bad, col])} "
            f"(줄 {_rows(bad)}). 쓸 수 있는 값: {', '.join(allowed[:10])}{' 등' if len(allowed) > 10 else ''}",
        )
    else:
        report.add(PASS, f"{label}({col}) 값이 모두 올발라요.")


def validate_flow_frame(df: pd.DataFrame) -> ValidationReport:
    report = ValidationReport(row_count=len(df))
    if df.empty:
        report.add(ERROR, "파일에 데이터 행이 없어요.")
        return report

    df = df.apply(lambda s: s.str.strip())
    missing = [c for c in COLUMNS if c not in df.columns]
    extra = [c for c in df.columns if c not in COLUMNS]
    if missing:
        report.add(
            ERROR,
            f"필수 컬럼 {len(missing)}개가 없어요: {', '.join(missing)}. "
            "4-11 내국인 유동인구(읍면동) 명세의 영문 컬럼명과 같은지 확인해 주세요.",
        )
    else:
        report.add(PASS, f"필수 컬럼 {len(COLUMNS)}개가 모두 있어요.")
    if extra:
        report.add(WARN, f"명세에 없는 컬럼이 있어요: {', '.join(extra)}. 분석에는 쓰지 않아요.")

    present = [c for c in COLUMNS if c in df.columns]
    empty = {c: df[c].eq("") for c in present}
    for col in [c for c in present if c not in POP_COLUMNS]:
        if empty[col].any():
            report.add(
                ERROR,
                f"{col} 컬럼에 빈 값이 {empty[col].sum():,}행 있어요 (줄 {_rows(empty[col])}).",
            )

    dates = None
    if "base_date" in df:
        dates = pd.to_datetime(df["base_date"], format="%Y%m%d", errors="coerce")
        bad = dates.isna() & ~empty["base_date"]
        if bad.any():
            report.add(
                ERROR,
                f"날짜(base_date)가 YYYYMMDD 형식(예: 20250512)이 아닌 행이 {bad.sum():,}행 있어요: "
                f"{_values(df.loc[bad, 'base_date'])} (줄 {_rows(bad)}).",
            )
        else:
            report.add(PASS, "날짜(base_date) 형식이 올발라요.")
        if dates.notna().any():
            report.period = (dates.min().strftime("%Y-%m-%d"), dates.max().strftime("%Y-%m-%d"))

    if dates is not None and {"pt_year", "pt_month"} <= set(df.columns):
        year_ok = df["pt_year"].eq(dates.dt.year.astype("Int64").astype(str))
        month = pd.to_numeric(
            df["pt_month"].where(df["pt_month"].str.fullmatch(r"\d{1,2}")), errors="coerce"
        )
        month_ok = month.eq(dates.dt.month)
        bad = dates.notna() & ~(year_ok & month_ok)
        if bad.any():
            report.add(
                WARN,
                f"년·월(pt_year, pt_month)이 날짜와 다른 행이 {bad.sum():,}행 있어요 (줄 {_rows(bad)}).",
            )

    if "time" in df:
        bad = ~df["time"].str.fullmatch(r"0?[1-9]|1\d|2[0-4]")
        if bad.any():
            report.add(
                ERROR,
                f"시간(time)은 1~24(또는 01~24)여야 하는데 다른 값이 {bad.sum():,}행 있어요: "
                f"{_values(df.loc[bad, 'time'])} (줄 {_rows(bad)}).",
            )
        else:
            report.add(PASS, "시간(time) 값이 모두 1~24 사이예요.")

    if "emd_cd" in df:
        _check_allowed(report, df, "emd_cd", list(EMD_CODES), "행정동코드")
        if "emd_nm" in df:
            known = df["emd_cd"].isin(EMD_CODES)
            wrong = known & df["emd_nm"].ne(df["emd_cd"].map(EMD_CODES))
            if wrong.any():
                report.add(
                    WARN,
                    f"행정동코드와 행정동명이 맞지 않는 행이 {wrong.sum():,}행 있어요 (줄 {_rows(wrong)}). 코드를 기준으로 봐요.",
                )
    for col, allowed, label in [
        ("dstrct_se", DISTRICTS, "지역구분"),
        ("sex", SEXES, "성별"),
        ("resd", RESIDENCES, "거주지"),
        ("age", [AGE_SKT_UNDER10, *AGE_SKT, *AGE_KT], "연령대"),
    ]:
        if col in df:
            _check_allowed(report, df, col, allowed, label)
    if "age" in df:
        has_skt = df["age"].isin([AGE_SKT_UNDER10, *AGE_SKT]).any()
        has_kt = df["age"].isin(AGE_KT).any()
        if has_skt and has_kt:
            report.add(
                WARN,
                "연령대에 SKT 형식(예: 2024)과 KT 형식(예: 20)이 섞여 있어요. 연령별 비교는 형식을 맞춘 뒤에 해요.",
            )

    pops = {}
    for col in [c for c in POP_COLUMNS if c in df]:
        pops[col] = pd.to_numeric(df[col], errors="coerce")
        not_number = pops[col].isna() & ~empty[col]
        if not_number.any():
            report.add(
                ERROR,
                f"{col} 컬럼에 숫자가 아닌 값이 {not_number.sum():,}행 있어요: {_values(df.loc[not_number, col])} (줄 {_rows(not_number)}).",
            )
        negative = pops[col] < 0
        if negative.any():
            report.add(
                ERROR, f"{col} 컬럼에 음수가 {negative.sum():,}행 있어요 (줄 {_rows(negative)})."
            )
        if empty[col].any():
            report.add(
                WARN,
                f"{col} 컬럼에 빈 값이 {empty[col].sum():,}행 있어요. 지우지 않고 빈 값으로 두고 집계해요.",
            )
    if pops and all(c in pops for c in POP_COLUMNS):
        report.add(PASS, "인구 컬럼 3개를 숫자로 읽었어요.")

    if set(KEY_COLUMNS) <= set(df.columns):
        dup = df.duplicated(KEY_COLUMNS, keep=False)
        if dup.any():
            report.add(
                WARN,
                f"날짜·시간·행정동·성별·연령·거주지가 같은 행이 {dup.sum():,}행 겹쳐요 (줄 {_rows(dup)}). 집계하면 두 번 더해져요.",
            )
        if {"base_date", "emd_cd", "time"} <= set(df.columns):
            hours = df.groupby(["base_date", "emd_cd"])["time"].nunique()
            short = hours[hours < 24]
            if len(short):
                report.add(
                    WARN,
                    f"시간대가 24개보다 적은 날짜·행정동이 {len(short):,}곳 있어요. 시간대별 비교에서 해당 시간이 비어 보여요.",
                )

    if "emd_nm" in df:
        known = df["emd_cd"].isin(EMD_CODES) if "emd_cd" in df else pd.Series(True, index=df.index)
        report.regions = sorted(df.loc[known, "emd_nm"].unique())

    if report.status != ERROR:
        clean = df[COLUMNS].copy()
        clean["base_date"] = dates
        clean["time"] = clean["time"].astype(int)
        for col in POP_COLUMNS:
            clean[col] = pops[col]
        report.data = clean
    return report


def validate_flow(source) -> ValidationReport:
    """CSV 파일(경로·바이트·업로드 객체)을 읽어 검증한다. 어떤 경우에도 예외를 던지지 않는다."""
    df, error = read_flow_csv(source)
    if error:
        report = ValidationReport()
        report.add(ERROR, error)
        return report
    try:
        return validate_flow_frame(df)
    except Exception as exc:  # noqa: BLE001 - 예상 못 한 형식도 앱이 멈추지 않게
        report = ValidationReport(row_count=len(df))
        report.add(
            ERROR,
            f"검사 중 예상하지 못한 문제가 생겼어요 ({type(exc).__name__}). 파일 형식을 확인해 주세요.",
        )
        return report
