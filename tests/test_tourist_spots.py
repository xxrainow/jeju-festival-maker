import pandas as pd

from analytics.area_link import load_wifi_ap
from analytics.tourist_spots import (
    CONFIRMED,
    METHOD_AP,
    METHOD_AP_ALIAS,
    METHOD_MULTI,
    METHOD_WEB,
    NEEDS_CHECK,
    build_draft,
    load_spot_areas,
)


def wifi_ap(tmp_path) -> pd.DataFrame:
    path = tmp_path / "ap.csv"
    path.write_text(
        "apGroupName,addressDong,latitude,longitude\n"
        "해녀박물관 #1,제주특별자치도 제주시 구좌읍 하도리,33.52,126.86\n"
        "서귀포감귤박물관,제주특별자치도 서귀포시 신효동,33.27,126.60\n"
        "천지연폭포,제주특별자치도 서귀포시 서홍동,33.24,126.55\n"
        "천지연폭포,제주특별자치도 서귀포시 서귀동,33.24,126.56\n",
        encoding="utf-8-sig",
    )
    return load_wifi_ap(path)


def test_draft_methods(tmp_path):
    names = [
        "해녀 박물관",
        "감귤박물관",
        "한라산국립공원",
        "국립제주박물관",
        "천지연폭포",
        "없는곳",
    ]
    draft = build_draft(names, wifi_ap(tmp_path)).set_index("sight_name")
    assert draft.loc["해녀 박물관", "method"] == METHOD_AP  # 공백 무시
    assert draft.loc["해녀 박물관", "area"] == "제주시 구좌읍"
    assert draft.loc["해녀 박물관", "area_level"] == "읍면"
    assert draft.loc["감귤박물관", "method"] == METHOD_AP_ALIAS
    assert draft.loc["감귤박물관", "area_level"] == "법정동"
    assert draft.loc["한라산국립공원", "method"] == METHOD_MULTI
    assert pd.isna(draft.loc["한라산국립공원", "area"])
    assert draft.loc["국립제주박물관", "method"] == METHOD_WEB
    assert draft.loc["국립제주박물관", "source"].startswith("https://")
    # AP 주소가 여러 동이면 고르지 않음
    assert pd.isna(draft.loc["천지연폭포", "area"])
    assert "여러 곳" in draft.loc["천지연폭포", "note"]
    assert draft.loc["없는곳", "method"] == "못 찾음"
    assert (draft["confirmed"] == NEEDS_CHECK).all()


def test_only_confirmed_rows_are_used(tmp_path):
    path = tmp_path / "areas.csv"
    pd.DataFrame(
        {
            "sight_name": ["가", "나", "다", "라"],
            "method": [METHOD_AP, METHOD_AP, METHOD_MULTI, METHOD_WEB],
            "area": ["제주시 구좌읍", "제주시 한림읍", None, None],
            "area_level": ["읍면", "읍면", None, None],
            "confirmed": [CONFIRMED, NEEDS_CHECK, CONFIRMED, CONFIRMED],
        }
    ).to_csv(path, index=False, encoding="utf-8-sig")
    assert load_spot_areas(path)["sight_name"].tolist() == ["가"]
