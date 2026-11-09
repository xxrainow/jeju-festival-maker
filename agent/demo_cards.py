"""B 화면 연결용 데모 아이디어 카드 (설계 기획서 9-2절 "애월 감귤" 예시).

숫자(신설 수, 신설리프트, 제주 축제 수, 예산 중앙값, 소규모 사례)는 문체부 2024~2026 실데이터 값이다.
이름·컨셉·가설 문장과 추천 월은 예시로 쓴 값이고, 관광객 관심 지표는 데이터 대기(pending)다.
API 키, 네트워크, 문체부 원자료 없이 동작한다.
"""

from agent.draft_contracts import IdeaProposal, UserRequest

DEMO_NOTICE = (
    "데모 응답이에요. 숫자는 문체부 2024~2026 실제 값이지만, 아이디어 이름과 문장은 예시이고 "
    "관광객 관심 지표는 아직 없어요."
)

DEMO_REQUEST = UserRequest(
    region="제주시 애월읍",
    purpose="지역 상권 활성화",
    interest="감귤",
    budget_max_krw=10_000_000,
    season="겨울",
    target="가족",
)

_TREND_SOURCE = "문체부 지역축제 2024-2026"
_JEJU_SOURCE = "제주 축제 목록 (문체부 지역축제 2026)"


def _interpretation(ref: dict) -> dict:
    """데모 카드의 형식은 모두 공급 ↑라서 지정 사례 유무로만 해석이 갈린다 (기획서 4절)."""
    if ref.get("designated_festivals"):
        return {"interpretation": "검증된 성장 분야", "strategy": "차별화 포인트 확보"}
    return {"interpretation": "신흥·선점 기회", "strategy": "먼저 자리 잡기"}


def _card(rank, title, concept, fmt, match, reason, new_count, lift, ref, median, examples, hyps):
    return {
        "idea_id": f"idea_{rank:03d}",
        "rank": rank,
        "score": None,
        "title": title,
        "concept": concept,
        "format": fmt,
        "material": "감귤",
        "material_category": "농산물",
        "purpose_match": match,
        "pick_reason": reason,
        "evidence": {
            "trend": {
                "new_count": new_count,
                "new_lift": lift,
                "verdict": "확실한 상승",
                **_interpretation(ref),
                "source": _TREND_SOURCE,
            },
            "jeju_gap": {"jeju_count": 0, "source": _JEJU_SOURCE},
            "visitor_interest": {"source": "와이파이 AP별 이용 현황", "status": "pending"},
        },
        "reference": ref,
        "timing": {
            "recommended_months": [12],
            "jeju_festivals_in_month": 1,
            "sources": [_JEJU_SOURCE],
        },
        "budget": {
            "input_krw": 10_000_000,
            "format_median_krw": median,
            "scale": "소규모 버전",
            "small_examples": examples,
            "source": "문체부 지역축제 2026",
        },
        "hypotheses": hyps,
        "existing_jeju_festivals": [
            {"name": "2026 효돈감귤꽃축제", "month": 5},
            {"name": "제4회 의귀리 귤꽃축제", "month": 5},
        ],
    }


_DEMO = {
    "input": DEMO_REQUEST.model_dump(),
    "applied_rules": {
        "material_category": "농산물",
        "pairing_passed": ["시장·상권", "정원·가드닝", "푸드·디저트", "맥주·주류", "도심·거리·골목", "야간·빛·드론"],
        "season_excluded": ["여름·물놀이"],
        "purpose_boosted": ["시장·상권", "푸드·디저트", "도심·거리·골목"],
    },
    "ideas": [
        _card(1, "애월 감귤 로컬 마켓", "수확철 감귤과 지역 가게가 함께 여는 주말 마켓", "시장·상권",
              "일치", "상권 활성화 목적과 가장 직접 맞고, 제주에 같은 형식 축제가 없어요",
              16, 3.6, {"type": "선점 기회"}, 60_000_000,
              [{"name": "제3회 나전역 야시장 야밤바 행사", "budget_krw": 5_000_000}],
              ["12월 애월읍 외지인 방문이 충분하다", "후보 장소 근처에 버스 접근성이 있다"]),
        _card(2, "감귤 디저트 페스타", "애월 카페·베이커리가 감귤 메뉴로 참여하는 디저트 축제",
              "푸드·디저트", "일치", "마켓과 달리 카페·베이커리가 주체라 참여 방식이 달라요",
              22, 2.82,
              {"type": "성공 사례", "designated_festivals": [
                  {"name": "강릉커피축제", "grade": "문화관광"},
                  {"name": "김천김밥축제", "grade": "예비"}]},
              278_000_000, [],
              ["관광객의 디저트·카페 소비가 많다", "참여 가능한 가게가 충분하다"]),
        _card(3, "귤빛 겨울정원", "감귤밭을 정원처럼 꾸민 가족 산책 축제", "정원·가드닝",
              "부분 일치", "앞의 둘과 달리 체류형 산책이라 가족 대상에 맞아요",
              10, 2.95, {"type": "선점 기회"}, 200_000_000, [],
              ["12월 추위·바람이 야외 체류를 막지 않는다", "참여할 감귤 농가를 확보할 수 있다"]),
    ],
    "is_demo": True,
    "notices": [DEMO_NOTICE],
}  # fmt: skip


def demo_proposal() -> IdeaProposal:
    """데모 카드 묶음의 새 복사본."""
    return IdeaProposal.model_validate(_DEMO)
