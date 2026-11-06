from datetime import date

import pandas as pd
import pytest

from analytics.visit_pattern import hourly_chart, hourly_visits, small_value_warning, visit_pattern
from schemas.contracts import AnalysisRequest


def flow(rows) -> pd.DataFrame:
    """(날짜, 동네, 시간, 방문인구) 목록으로 검증을 통과한 형태의 표를 만든다."""
    codes = {"서귀포시 성산읍": "50130259", "제주시 추자면": "50110320"}
    return pd.DataFrame(
        {
            "base_date": [pd.Timestamp(d) for d, *_ in rows],
            "emd_nm": [n for _, n, *_ in rows],
            "emd_cd": [codes[n] for _, n, *_ in rows],
            "time": [h for *_, h, _ in rows],
            "visit_pop_cnt": [v for *_, v in rows],
        }
    )


DATA = flow(
    [
        ("2025-05-16", "서귀포시 성산읍", 3, 20.0),
        ("2025-05-16", "서귀포시 성산읍", 14, 100.0),
        ("2025-05-17", "서귀포시 성산읍", 3, 30.0),
        ("2025-05-17", "서귀포시 성산읍", 14, 150.0),
        ("2025-05-16", "제주시 추자면", 14, 4.0),
        ("2025-05-17", "제주시 추자면", 14, 3.0),
    ]
)


def request(regions, start="2025-05-16", end="2025-05-17") -> AnalysisRequest:
    return AnalysisRequest(
        idea_id="idea-1",
        regions=regions,
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
    )


def test_hourly_visits_sum_and_daily_average():
    table = hourly_visits(DATA).set_index(["emd_nm", "hour"])
    assert table.loc[("서귀포시 성산읍", 14), "visit_pop"] == 250
    assert table.loc[("서귀포시 성산읍", 14), "visit_pop_daily"] == 125
    assert table["visit_pop"].sum() == DATA["visit_pop_cnt"].sum()


def test_small_values_are_warned():
    warning = small_value_warning(hourly_visits(DATA))
    assert "10 미만 값이 1개" in warning and "제주시 추자면 14시" in warning
    assert small_value_warning(hourly_visits(DATA[DATA["emd_nm"] == "서귀포시 성산읍"])) is None


def test_result_metrics_and_synthetic_flag():
    result, table = visit_pattern(DATA, request(["서귀포시 성산읍"]), is_synthetic=True)
    assert result.is_synthetic is True
    assert result.warnings[0].startswith("가상 데이터")
    assert result.metrics["visit_pop_total"] == 300
    assert result.metrics["peak_hour"] == 14
    assert result.metrics["daytime_share_pct"] == pytest.approx(250 / 300 * 100)
    assert result.metrics["weekend_to_weekday_ratio"] == pytest.approx(180 / 120)
    assert set(table["emd_nm"]) == {"서귀포시 성산읍"}


def test_region_by_code_missing_region_and_no_weekend():
    result, _ = visit_pattern(
        DATA, request(["50110320", "제주시 우도면"], end="2025-05-16"), is_synthetic=False
    )
    text = " ".join(result.warnings)
    assert "제주시 우도면" in text
    assert "주말과 평일" in text
    assert "10 미만" in text
    assert not any(w.startswith("가상 데이터") for w in result.warnings)


def test_empty_selection_returns_warning_not_error():
    result, table = visit_pattern(DATA, request(["제주시 우도면"]), is_synthetic=True)
    assert table.empty and result.metrics == {}
    assert any("자료가 없어요" in w for w in result.warnings)


def test_chart_title_marks_synthetic():
    fig = hourly_chart(hourly_visits(DATA), is_synthetic=True)
    assert "가상 데이터" in fig.layout.title.text
    assert len(fig.data) == 2
