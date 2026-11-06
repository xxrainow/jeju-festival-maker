"""분석 기본 기간.

- 여러 데이터를 같이 비교하는 분석: 모든 데이터가 겹치는 2023-01 ~ 2024-12
- 단일 데이터 후보지 분석: 2023-01 ~ 2025-10 (2022년 버스 이상일 판정 불안정 구간 제외)
- 최근 패턴 확인: 2025-01 ~ 2025-10 (비교 분석과 섞지 않고 따로 표시)

기간은 analysis_period()로 바꿔 쓸 수 있다.
"""

import calendar
from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class AnalysisPeriod:
    start_month: str  # YYYYMM
    end_month: str  # YYYYMM

    def __post_init__(self):
        for month in (self.start_month, self.end_month):
            if len(month) != 6 or not month.isdigit() or not 1 <= int(month[4:]) <= 12:
                raise ValueError(f"기간은 YYYYMM 형식이어야 합니다: {month}")
        if self.end_month < self.start_month:
            raise ValueError("끝 월이 시작 월보다 앞섭니다")

    @property
    def start_date(self) -> date:
        return date(int(self.start_month[:4]), int(self.start_month[4:]), 1)

    @property
    def end_date(self) -> date:
        year, month = int(self.end_month[:4]), int(self.end_month[4:])
        return date(year, month, calendar.monthrange(year, month)[1])

    def label(self) -> str:
        return f"{self.start_month[:4]}-{self.start_month[4:]} ~ {self.end_month[:4]}-{self.end_month[4:]}"

    def filter_months(self, df: pd.DataFrame, column: str = "base_year_month") -> pd.DataFrame:
        """YYYYMM 문자열 열 기준으로 기간 안의 행만 남긴다."""
        months = df[column].astype(str)
        return df[(months >= self.start_month) & (months <= self.end_month)]

    def filter_dates(self, df: pd.DataFrame, column: str = "base_date") -> pd.DataFrame:
        """날짜 열 기준으로 기간 안의 행만 남긴다."""
        dates = pd.to_datetime(df[column]).dt.date
        return df[(dates >= self.start_date) & (dates <= self.end_date)]


COMPARISON_PERIOD = AnalysisPeriod("202301", "202412")
CANDIDATE_PERIOD = AnalysisPeriod("202301", "202510")
RECENT_PERIOD = AnalysisPeriod("202501", "202510")


def analysis_period(
    start_month: str | None = None,
    end_month: str | None = None,
    default: AnalysisPeriod = COMPARISON_PERIOD,
) -> AnalysisPeriod:
    """기본 기간에서 시작·끝 월만 바꾼 기간."""
    return AnalysisPeriod(start_month or default.start_month, end_month or default.end_month)
