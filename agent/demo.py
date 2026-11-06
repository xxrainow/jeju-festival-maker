"""B 화면 연결용 데모 응답. API 키와 네트워크 없이 계약에 맞는 사례와 아이디어를 준다.

모두 가상 자료다. 실제 기사나 검색 결과가 아니므로 제목에 [가상]을 붙이고,
화면에서도 데모임을 드러낸다 (CLAUDE.md 3절: 합성 데이터 표시).
"""

from datetime import UTC, date, datetime

from schemas.contracts import FestivalCase, FestivalIdea

# 데모 사례의 수집 시점. 실제 수집이 아니므로 고정값을 쓴다.
DEMO_RETRIEVED_AT = datetime(2026, 11, 6, 0, 0, tzinfo=UTC)

DEMO_CASES = [
    FestivalCase(
        case_id="case_demo_coffee",
        title="[가상] ○○군 커피 축제, 지역 농가 참여 시음 체험 운영",
        source_url="https://example.com/demo/coffee-festival",
        published_at=date(2026, 10, 21),
        event_date=None,
        retrieved_at=DEMO_RETRIEVED_AT,
        evidence_text="지역 농가가 직접 참여하는 시음 부스와 원두 판매 마켓을 함께 운영했다고 밝혔다.",
        evidence_status="snippet_only",
    ),
    FestivalCase(
        case_id="case_demo_village",
        title="[가상] △△읍 골목 축제, 상점 스탬프 투어와 마을 산책 프로그램",
        source_url="https://example.com/demo/village-festival",
        published_at=date(2026, 9, 30),
        event_date=None,
        retrieved_at=DEMO_RETRIEVED_AT,
        evidence_text="참여 상점을 도는 스탬프 투어와 주민 해설 산책을 묶어 운영했다고 소개했다.",
        evidence_status="snippet_only",
    ),
]

DEMO_IDEAS = [
    FestivalIdea(
        idea_id="idea_001",
        title="감귤 테이블",
        summary="감귤 시음·디저트 체험과 지역 생산자 마켓을 연결하는 1일 축제",
        programs=["감귤 음료·디저트 시식", "생산자와 함께하는 감귤 이야기", "지역 상품 판매 마켓"],
        target_audience=["가족 단위 관광객", "인근 주민"],
        rationale="참고 사례의 '생산자 참여 시음 + 판매 마켓' 구조를 제주 감귤 생산자와 연결할 수 있다는 가설입니다.",
        case_ids=["case_demo_coffee"],
        assumptions=["참여 가능한 감귤 농가 확인 필요", "개최 시기의 감귤 수급 확인 필요"],
    ),
    FestivalIdea(
        idea_id="idea_002",
        title="동네 발견 산책",
        summary="마을 산책과 공방 체험, 상점 스탬프 투어를 연결하는 참여형 축제",
        programs=["주민 해설 마을 산책", "지역 공방 미니 체험", "참여 상점 스탬프 투어"],
        target_audience=["도보 여행을 선호하는 관광객", "지역 문화에 관심 있는 방문객"],
        rationale="참고 사례의 '스탬프 투어 + 주민 해설 산책' 방식으로 마을 안 체류를 늘릴 수 있다는 가설입니다.",
        case_ids=["case_demo_village"],
        assumptions=["실제 보행 경로와 접근성 확인 필요", "주민과 참여 상점 협의 필요"],
    ),
    FestivalIdea(
        idea_id="idea_003",
        title="저녁 로컬 마켓",
        summary="지역 먹거리·수공예 마켓과 소규모 공연을 묶은 저녁 축제",
        programs=["지역 먹거리 부스", "수공예 판매·체험", "소규모 음악 공연"],
        target_audience=["저녁 활동을 찾는 관광객", "인근 주민"],
        rationale="두 사례의 '생산자 판매'와 '상점 연계'를 저녁 시간대 마켓으로 묶을 수 있다는 가설이며, 방문 패턴 분석으로 적합성을 검토해야 합니다.",
        case_ids=["case_demo_coffee", "case_demo_village"],
        assumptions=["저녁 시간대 방문 패턴과 귀가 교통편 확인 필요", "행사장의 야간 운영·소음·조명 조건 확인 필요"],
    ),
]


def demo_cases() -> list[FestivalCase]:
    """데모 사례의 복사본. 화면에서 바꿔도 원본은 그대로다."""
    return [case.model_copy(deep=True) for case in DEMO_CASES]


def demo_ideas() -> list[FestivalIdea]:
    """데모 아이디어 3개의 복사본."""
    return [idea.model_copy(deep=True) for idea in DEMO_IDEAS]
