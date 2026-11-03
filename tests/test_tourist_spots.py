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
    fill_admin_areas,
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
            "area": ["제주시 구좌읍", "제주시 한림읍", None, "서귀포시 서귀동"],
            "area_level": ["읍면", "읍면", None, "법정동"],
            "admin_area": ["제주시 구좌읍", "제주시 한림읍", None, None],
            "confirmed": [CONFIRMED, NEEDS_CHECK, CONFIRMED, CONFIRMED],
        }
    ).to_csv(path, index=False, encoding="utf-8-sig")
    assert load_spot_areas(path)["sight_name"].tolist() == ["가"]


def test_fill_admin_areas():
    mapping = pd.DataFrame(
        {
            "legal_dong": [
                "제주시 건입동",
                "제주시 건입동",
                "서귀포시 서귀동",
                "서귀포시 서귀동",
                "제주시 회천동",
            ],
            "admin_dong": [
                "제주시 건입동",
                "제주시 일도1동",
                "서귀포시 천지동",
                "서귀포시 송산동",
                "제주시 봉개동",
            ],
            "used": [True, False, True, True, False],
        }
    )
    table = pd.DataFrame(
        {
            "sight_name": [
                "읍면",
                "AP 좌표",
                "AP 여러 동",
                "변환",
                "애매",
                "근거 부족",
                "직접 확인",
            ],
            "method": [
                METHOD_AP,
                METHOD_AP,
                METHOD_AP,
                METHOD_WEB,
                METHOD_WEB,
                METHOD_WEB,
                METHOD_WEB,
            ],
            "area": [
                "제주시 애월읍",
                "제주시 일도이동",
                "서귀포시 서홍동",
                "제주시 건입동",
                "서귀포시 서귀동",
                "제주시 회천동",
                "서귀포시 서귀동",
            ],
            "area_level": ["읍면", "법정동", "법정동", "법정동", "법정동", "법정동", "법정동"],
            "coord_admin_ref": [
                "제주시 애월읍",
                "제주시 일도2동",
                "서귀포시 정방동 / 서귀포시 천지동",
                None,
                None,
                None,
                None,
            ],
            "admin_area": [None, None, None, None, None, None, "서귀포시 천지동"],
            "admin_method": [None, None, None, None, None, None, "지도 확인"],
        }
    )
    out = fill_admin_areas(table, mapping).set_index("sight_name")
    assert out["admin_area"].tolist() == [
        "제주시 애월읍",
        "제주시 일도2동",
        None,
        "제주시 건입동",  # 오류 의심 짝(일도1동)은 근거에서 빠짐
        None,
        None,
        "서귀포시 천지동",
    ]
    assert out.loc["AP 좌표", "admin_method"] == "AP 좌표"
    assert out.loc["AP 여러 동", "admin_method"].startswith("AP 좌표 여러 행정동")
    assert out.loc["변환", "admin_method"] == "변환표"
    assert out.loc["애매", "admin_method"].startswith("변환표 애매함")
    assert out.loc["근거 부족", "admin_method"] == "변환표 근거 부족"
    assert out.loc["직접 확인", "admin_method"] == "지도 확인"
