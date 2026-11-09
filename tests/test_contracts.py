import pytest
from pydantic import ValidationError

from schemas.contracts import AnalysisRequest, FestivalIdea, UserRequest

# B에게 공유한 예시 입출력과 같은 값이다. 바꾸면 B에게도 알린다.
IDEA_EXAMPLE = {
    "idea_id": "idea_001",
    "title": "감귤 테이블",
    "summary": "감귤 시음·디저트 체험과 지역 생산자 마켓을 연결하는 1일 축제",
    "programs": ["감귤 음료·디저트 시식", "생산자와 함께하는 감귤 이야기", "지역 상품 판매 마켓"],
    "target_audience": ["가족 단위 관광객", "인근 주민"],
    "rationale": "참고 사례의 '생산자 참여 시음 + 판매 마켓' 구조를 제주 감귤 생산자와 연결할 수 있다는 가설입니다.",
    "assumptions": ["참여 가능한 생산자 확인 필요", "개최 시기의 감귤 수급과 행사장 조건 확인 필요"],
    "status": "unreviewed",
}


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


def test_idea_example_is_valid():
    idea = FestivalIdea.model_validate(IDEA_EXAMPLE)
    assert idea.target_audience[0] == "가족 단위 관광객"


@pytest.mark.parametrize("audience", [[], ["a", "b", "c", "d"], "가족 단위 관광객"])
def test_idea_audience_must_be_list_of_one_to_three(audience):
    with pytest.raises(ValidationError):
        FestivalIdea.model_validate({**IDEA_EXAMPLE, "target_audience": audience})


def test_idea_requires_rationale():
    data = {k: v for k, v in IDEA_EXAMPLE.items() if k != "rationale"}
    with pytest.raises(ValidationError):
        FestivalIdea.model_validate(data)
