import pandas as pd
import pytest

from agent.draft_contracts import UserRequest
from agent.idea_gen import build_candidates, build_card, load_materials, materials_from_dictionary
from research.materials import (
    KEYWORDS_PATH,
    NEUTRAL_INTEREST,
    build_dictionary,
    jeju_festivals,
    latest_festivals,
    load_keywords,
    materials_path,
    wifi_place_shares,
)

KEYWORDS = pd.DataFrame(
    {
        "material": ["유채꽃", "방어", "해녀", "감귤"],
        "category": ["자연", "수산물", "문화·생활", "농산물"],
        "keywords": ["유채", "방어", "해녀", "감귤|귤꽃"],
        "seasonal": [True, True, False, True],
        "manual_months": [(), (), (), (11, 12, 1)],
        "manual_months_basis": ["", "", "", "기획서 7절"],
        "note": ["", "", "", ""],
    }
)


def panel() -> pd.DataFrame:
    rows = [
        ("제주", "제40회 서귀포유채꽃축제", 3, 2026), ("제주", "제40회 서귀포유채꽃축제", 3, 2025),
        ("제주", "최남단 방어 축제", 11, 2026), ("제주", "제주해녀축제", 9, 2026),
        ("제주", "효돈 귤꽃축제", 5, 2026),
        ("서울", "한강 유채꽃 축제", 4, 2026), ("부산", "기장 멸치축제", 4, 2026),
        ("부산", "전통 문화제", 5, 2026), ("부산", "해운대 모래축제", 5, 2026),
    ]  # fmt: skip
    return pd.DataFrame(rows, columns=["시도", "축제명", "월", "연도"])


def usage() -> pd.DataFrame:
    rows = [
        ("녹산로 유채꽃길", "202305", "관광", 80), ("녹산로 유채꽃길", "202305", "거주", 20),
        ("해녀박물관", "202306", "관광", 50), ("해녀박물관", "202306", "업무", 50),
        ("버스정류소_해녀박물관[동]", "202306", "관광", 999),  # 정류소는 뺀다
        ("녹산로 유채꽃길", "202503", "관광", 0), ("녹산로 유채꽃길", "202503", "거주", 999),  # 기간 밖
        ("일반 공원", "202307", "관광", 10), ("일반 공원", "202307", "거주", 90),
    ]  # fmt: skip
    return pd.DataFrame(
        rows, columns=["wifi_place_name", "base_year_month", "visit_type", "use_amount"]
    )


def test_keyword_table_is_valid():
    kw = load_keywords(KEYWORDS_PATH)
    assert kw["material"].is_unique
    assert set(kw["category"]) <= {"자연", "농산물", "수산물", "문화·생활", "경관"}
    assert len(kw) >= 30


def test_festivals_deduplicated_across_years():
    fests = jeju_festivals(panel(), None)
    assert (fests["축제명"] == "제40회 서귀포유채꽃축제").sum() == 1
    assert set(fests["출처"]) == {"문체부"}


def test_match_places_false_skips_wifi(trend_data):
    kw = KEYWORDS.copy()
    kw["match_places"] = [True, True, False, True]  # 해녀 장소 연결 끔
    d, review = build_dictionary(panel(), None, wifi_place_shares(usage()), kw)
    d = d.set_index("material")
    assert d.loc["해녀", "place_count"] == 0
    assert d.loc["해녀", "interest_status"] == "pending"
    assert not ((review["material"] == "해녀") & (review["kind"] == "와이파이 장소")).any()


def test_place_shares_use_interest_period_and_skip_facilities():
    places = wifi_place_shares(usage())
    assert "버스정류소_해녀박물관[동]" not in places.index
    assert places.loc["녹산로 유채꽃길", "tourist"] / places.loc["녹산로 유채꽃길", "total"] == 0.8


def test_dictionary_months_share_and_strength():
    d, review = build_dictionary(panel(), None, wifi_place_shares(usage()), KEYWORDS)
    d = d.set_index("material")
    # 제철 월: 계절 재료는 기존 제주 축제 월, 수동 입력이 있으면 그것
    assert d.loc["유채꽃", "months"] == "3"
    assert d.loc["방어", "months"] == "11"
    assert d.loc["해녀", "months"] == ""  # 계절 제약 없음
    assert d.loc["감귤", "months"] == "11|12|1" and d.loc["감귤", "festival_months"] == "5"
    # 관광 비중과 관심 지표
    assert d.loc["유채꽃", "tourist_share_pct"] == 80.0
    assert d.loc["해녀", "tourist_share_pct"] == 50.0
    assert d.loc["유채꽃", "interest"] == 1.0
    # 장소가 없는 재료는 관심 지표 pending, 강점은 중간값으로 계산 (희소성만으로 1등이 되지 않게)
    assert d.loc["방어", "interest_status"] == "pending"
    assert d.loc["방어", "strength"] == (NEUTRAL_INTEREST + d.loc["방어", "rarity"]) / 2
    # 전국에 흔한 재료일수록 희소성이 낮다
    assert d.loc["유채꽃", "rarity"] < d.loc["해녀", "rarity"]
    assert set(review["kind"]) == {"축제", "와이파이 장소"}


def test_dictionary_feeds_candidates_and_cards(trend_data):
    d, _ = build_dictionary(panel(), None, wifi_place_shares(usage()), KEYWORDS)
    mats = materials_from_dictionary(d)
    by_name = {m.name: m for m in mats}
    assert by_name["방어"].months == (11,) and by_name["해녀"].months is None
    assert by_name["유채꽃"].existing_festivals == (("제40회 서귀포유채꽃축제", 3),)
    assert by_name["감귤"].existing_festivals == (("효돈 귤꽃축제", 5),)

    req = UserRequest(interest="유채꽃")
    cset = build_candidates(req, trend_data, mats)
    assert cset.notices == []  # 사전을 쓰면 임시 목록 안내가 없다
    card = build_card(
        cset.candidates[0], 1, req, trend_data, title="t", concept="c", hypotheses=["h"]
    )
    ev = card.evidence.visitor_interest
    assert ev.status == "ready" and ev.value == 80.0 and "와이파이" in ev.source
    assert [(f.name, f.month) for f in card.existing_jeju_festivals] == [
        ("제40회 서귀포유채꽃축제", 3)
    ]

    req = UserRequest(interest="방어")
    cset = build_candidates(req, trend_data, mats)
    assert any("중간값" in n for n in cset.notices)
    card = build_card(
        cset.candidates[0], 1, req, trend_data, title="t", concept="c", hypotheses=["h"]
    )
    assert card.evidence.visitor_interest.status == "pending"


@pytest.mark.skipif(not materials_path().exists(), reason="실데이터 소재 사전 없음")
def test_real_dictionary_loads():
    mats = load_materials()
    assert len(mats) >= 30
    assert all(0 <= m.strength <= 1 for m in mats)


def test_latest_festivals_dedupes_years_and_keeps_month():
    rows = [
        ("제40회 서귀포유채꽃축제", 3, 2024),
        ("제42회 서귀포유채꽃축제", 4, 2026),
        ("가시리 유채 걷기", 3, 2025),
    ]
    hit = pd.DataFrame(rows, columns=["축제명", "월", "연도"])
    assert latest_festivals(hit) == [
        {"name": "가시리 유채 걷기", "month": 3},
        {"name": "제42회 서귀포유채꽃축제", "month": 4},
    ]


def test_existing_festivals_prefer_candidate_months(trend_data):
    from agent.idea_gen import Material

    fests = (("봄 축제", 4), ("여름 축제", 7), ("겨울 축제", 12), ("가을 축제", 10))
    mats = (Material("감귤", "농산물", (11, 12, 1), strength=0.8, existing_festivals=fests),)
    cand = build_candidates(UserRequest(interest="감귤"), trend_data, mats).candidates[0]
    assert cand.existing_festivals == [("겨울 축제", 12), ("봄 축제", 4), ("여름 축제", 7)]
