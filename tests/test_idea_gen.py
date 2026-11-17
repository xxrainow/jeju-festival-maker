import pytest

from agent.draft_contracts import UserRequest
from agent.idea_gen import (
    FORMATS,
    INTEREST_NOTICE,
    PAIRING,
    SEED_MATERIALS,
    build_candidates,
    build_card,
    pick_diverse,
    purpose_category,
    resolve_interest,
)

AEWOL = UserRequest(
    region="제주시 애월읍",
    purpose="지역 상권 활성화",
    interest="감귤",
    budget_max_krw=10_000_000,
    season="겨울",
    target="가족",
)


def test_pairing_table_matches_design_document():
    assert PAIRING["정원·가드닝"]["수산물"] == "✕"
    assert PAIRING["정원·가드닝"]["농산물"] == "○"
    assert PAIRING["도심·거리·골목"]["농산물"] == "△"


def test_resolve_interest():
    assert [m.name for m in resolve_interest("감귤 디저트", SEED_MATERIALS)[0]] == ["감귤"]
    assert {m.category for m in resolve_interest("수산물", SEED_MATERIALS)[0]} == {"수산물"}
    with pytest.raises(ValueError, match="한라봉"):
        resolve_interest("한라봉", SEED_MATERIALS)


def test_fixed_material_filters_pairing_and_season(trend_data):
    cset = build_candidates(AEWOL, trend_data)
    formats = [c.format for c in cset.candidates]
    assert {c.material for c in cset.candidates} == {"감귤"}
    assert "여름·물놀이" not in formats  # 궁합 ✕ + 겨울 제외
    assert "영화·책·아트" not in formats  # 궁합 ✕
    assert cset.rules.season_excluded == ["여름·물놀이"]
    assert cset.rules.material_category == "농산물"
    assert all(c.months == [12, 1] for c in cset.candidates)  # 감귤 제철 ∩ 겨울, 겨울 순서
    assert INTEREST_NOTICE in cset.notices


def test_triangle_halves_score_and_purpose_boosts(trend_data):
    cset = build_candidates(AEWOL, trend_data)
    by_format = {c.format: c for c in cset.candidates}
    night = by_format["야간·빛·드론"]  # 감귤 × 야간은 △
    assert night.pairing == "△"
    raw = sum(night.parts.values()) / 3
    assert abs(night.score - raw / 2) < 1e-3
    market = by_format["시장·상권"]
    assert market.purpose_boosted
    assert abs(market.score - (sum(market.parts.values()) / 3 + 0.1)) < 1e-3


def test_candidates_sorted_and_capped(trend_data):
    cset = build_candidates(UserRequest(), trend_data)
    scores = [c.score for c in cset.candidates]
    assert scores == sorted(scores, reverse=True)
    formats = [c.format for c in cset.candidates]
    assert len(formats) == len(set(formats)) >= 3  # 형식별 1개라 LLM이 형식을 겹치게 고를 수 없다
    assert max(sum(c.material == m for c in cset.candidates) for m in ("갈치", "방어")) <= 3
    assert [c.candidate_id for c in cset.candidates][:2] == ["cand_01", "cand_02"]


def test_best_per_format_keeps_top_score_of_each_format(trend_data):
    from agent.idea_gen import _best_per_format

    full = build_candidates(UserRequest(), trend_data, top_n=100)
    assert len({c.format for c in full.candidates}) == len(full.candidates)
    # 재료 상한(3)에 걸려도 그 형식에 다른 재료가 없으면 형식을 빼지 않는다
    one = [c for c in full.candidates[:1]]
    same = [c.model_copy(update={"format": f}) for c, f in zip(one * 5, FORMATS[:5], strict=False)]
    picked = _best_per_format(same, top_n=10, cap=3)
    assert [c.format for c in picked] == list(FORMATS[:5])


def test_pick_diverse_prefers_new_format_and_material(trend_data):
    picks = pick_diverse(build_candidates(UserRequest(), trend_data).candidates)
    assert len({p.format for p in picks}) == 3
    assert len({p.material for p in picks}) == 3


def test_build_card_fills_numbers_from_code(trend_data):
    cset = build_candidates(AEWOL, trend_data)
    market = next(c for c in cset.candidates if c.format == "시장·상권")
    card = build_card(
        market, 1, AEWOL, trend_data, title="애월 감귤 마켓", concept="c", hypotheses=["h"]
    )
    assert card.evidence.trend.new_count == 16
    assert card.evidence.jeju_gap.jeju_count == 0
    assert card.evidence.visitor_interest.status == "pending"
    assert card.reference.type == "선점 기회"
    assert card.budget.format_median_krw == 60_000_000
    assert card.budget.scale == "소규모 버전"
    assert [e.name for e in card.budget.small_examples] == ["작은 마켓"]
    assert card.timing.recommended_months == [12, 1]
    assert card.timing.jeju_festivals_in_month == 1
    assert card.purpose_match == "일치"
    assert card.evidence.trend.interpretation == "신흥·선점 기회"
    assert card.evidence.trend.strategy == "먼저 자리 잡기"
    food = next(c for c in cset.candidates if c.format == "푸드·디저트")
    food_card = build_card(food, 2, AEWOL, trend_data, title="t", concept="c", hypotheses=["h"])
    assert food_card.reference.type == "성공 사례"
    assert food_card.evidence.trend.interpretation == "검증된 성장 분야"


def test_year_round_candidate_gets_quiet_months(trend_data):
    req = UserRequest(interest="해녀")
    cand = build_candidates(req, trend_data).candidates[0]
    assert len(cand.months) == 12
    card = build_card(cand, 1, req, trend_data, title="t", concept="c", hypotheses=["h"])
    assert card.timing.recommended_months == [1, 2, 4]  # 제주 축제 0개인 달 중 앞의 3개
    assert card.purpose_match is None
    assert card.budget.scale == "기본" and card.budget.small_examples == []


@pytest.mark.parametrize(
    ("text", "category"),
    [
        ("지역 상권 활성화", "지역 상권 활성화"),
        ("상권 살리는", "지역 상권 활성화"),
        ("가게 매출 올리기", "지역 상권 활성화"),
        ("관광객 좀 끌고", "관광객 유치"),
        ("주민 화합", "주민 참여"),
        ("관광객 끌어서 상권 살리기", "관광객 유치"),  # 먼저 나온 말
        ("마을 홍보", None),
        ("", None),
        (None, None),
    ],
)
def test_purpose_category(text, category):
    assert purpose_category(text) == category


def test_free_text_purpose_gets_boost_and_match(trend_data):
    free = UserRequest(interest="감귤", season="겨울", purpose="상권 살리는")
    cset = build_candidates(free, trend_data)
    assert cset.rules.purpose_boosted == ["시장·상권", "푸드·디저트", "도심·거리·골목"]
    market = next(c for c in cset.candidates if c.format == "시장·상권")
    assert market.purpose_boosted
    card = build_card(market, 1, free, trend_data, title="t", concept="c", hypotheses=["h"])
    assert card.purpose_match == "일치"
    none = UserRequest(interest="감귤", purpose="마을 홍보")
    assert build_candidates(none, trend_data).rules.purpose_boosted == []
