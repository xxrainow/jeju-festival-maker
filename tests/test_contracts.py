import pytest
from pydantic import ValidationError

from schemas.contracts import AnalysisRequest, UserRequest


def test_unknown_budget_is_allowed():
    assert UserRequest(purpose="지역 상권 활성화").budget_max_krw is None


def test_negative_budget_is_rejected():
    with pytest.raises(ValidationError):
        UserRequest(purpose="지역 상권 활성화", budget_max_krw=-1)


def test_reversed_analysis_period_is_rejected():
    with pytest.raises(ValidationError):
        AnalysisRequest(
            idea_id="idea-1", regions=["A"], start_date="2026-11-02", end_date="2026-11-01"
        )
