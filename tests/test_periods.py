from datetime import date

import pandas as pd
import pytest

from analytics.periods import (
    CANDIDATE_PERIOD,
    COMPARISON_PERIOD,
    RECENT_PERIOD,
    AnalysisPeriod,
    analysis_period,
)


def test_default_periods():
    assert COMPARISON_PERIOD.label() == "2023-01 ~ 2024-12"
    assert CANDIDATE_PERIOD.label() == "2023-01 ~ 2025-10"
    assert RECENT_PERIOD.label() == "2025-01 ~ 2025-10"


def test_recent_period_does_not_overlap_comparison():
    assert RECENT_PERIOD.start_date > COMPARISON_PERIOD.end_date


def test_period_dates_cover_whole_months():
    assert CANDIDATE_PERIOD.start_date == date(2023, 1, 1)
    assert CANDIDATE_PERIOD.end_date == date(2025, 10, 31)
    assert AnalysisPeriod("202402", "202402").end_date == date(2024, 2, 29)


def test_period_can_be_changed():
    period = analysis_period(end_month="202406")
    assert period == AnalysisPeriod("202301", "202406")
    assert analysis_period("202405", default=RECENT_PERIOD) == AnalysisPeriod("202405", "202510")


@pytest.mark.parametrize(
    "start, end", [("2023-01", "202412"), ("202313", "202412"), ("202412", "202301")]
)
def test_invalid_period_is_rejected(start, end):
    with pytest.raises(ValueError):
        AnalysisPeriod(start, end)


def test_filter_months():
    df = pd.DataFrame({"base_year_month": ["202212", "202301", "202412", "202501"]})
    assert COMPARISON_PERIOD.filter_months(df)["base_year_month"].tolist() == ["202301", "202412"]


def test_filter_dates():
    df = pd.DataFrame(
        {"base_date": [date(2022, 12, 31), date(2023, 1, 1), date(2025, 10, 31), date(2025, 11, 1)]}
    )
    kept = CANDIDATE_PERIOD.filter_dates(df)["base_date"].tolist()
    assert kept == [date(2023, 1, 1), date(2025, 10, 31)]
