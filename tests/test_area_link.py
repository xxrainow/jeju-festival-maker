import pandas as pd
import pytest

from analytics.area_link import (
    AMBIGUOUS,
    LINKED,
    NO_ADDRESS,
    NOT_FOUND,
    area_level,
    candidate_city,
    link_bus_usage,
    link_wifi_places,
    load_bus_stations,
    load_wifi_ap,
    match_summary,
    nearest_area_reference,
    parse_area,
    station_id_from_wifi_name,
    wifi_category,
)

STATION_COLUMNS = "stationId,stationName,stationAddress,latitude,longitude\n"


def stations(tmp_path, rows: str) -> pd.DataFrame:
    path = tmp_path / "stations.csv"
    path.write_text(STATION_COLUMNS + rows, encoding="utf-8-sig")
    return load_bus_stations(path)


def wifi_ap(tmp_path, rows: str) -> pd.DataFrame:
    path = tmp_path / "ap.csv"
    path.write_text("apGroupName,addressDong\n" + rows, encoding="utf-8-sig")
    return load_wifi_ap(path)


@pytest.mark.parametrize(
    "address, expected",
    [
        ("제주시 일도2동", "제주시 일도2동"),
        ("서귀포시 대정읍 동일리", "서귀포시 대정읍"),
        ("제주특별자치도 제주시 삼도이동", "제주시 삼도이동"),
        ("제주특별자치도 서귀포시 안덕면 상창리", "서귀포시 안덕면"),
        ("서귀포시 표선면 세화리 ", "서귀포시 표선면"),
        ("제주특별자치도 서귀포시 온평리", None),
        ("귀덕리 493-1", None),
        (None, None),
    ],
)
def test_parse_area(address, expected):
    assert parse_area(address) == expected


def test_area_level():
    assert area_level("서귀포시 대정읍", "행정동") == "읍면"
    assert area_level("제주시 우도면", "법정동") == "읍면"
    assert area_level("제주시 일도2동", "행정동") == "행정동"
    assert area_level(None, "행정동") is None


def test_station_id_from_wifi_name():
    assert station_id_from_wifi_name("버스정류소_효돈초등학교_(효돈중학교방면)_[406000459]") == (
        "406000459"
    )
    assert station_id_from_wifi_name("서홍동복지회관 버스정류소(406000491)") == "406000491"
    assert station_id_from_wifi_name("버스정류소_반석아파트[동]") is None


def test_wifi_category():
    assert wifi_category("버스정류소_반석아파트[동]") == "버스정류소"
    assert wifi_category("전기차충전소_제주보건소") == "전기차충전소"
    assert wifi_category("1-93호공원") == "공원"
    assert wifi_category("17코스") == "올레·코스"
    assert wifi_category("중앙도서관") == "기타"


def test_lot_number_address_drops_dong_but_keeps_digit_dong(tmp_path):
    df = stations(
        tmp_path,
        "1,선궷내,제주특별자치도 서귀포시 대포동 2309-1,33.2,126.4\n"
        "2,용흥리,제주특별자치도 제주시 애월읍 신엄리 1950-1,33.4,126.3\n"
        "3,관덕정,제주시 삼도2동,33.5,126.5\n",
    )
    assert df["area"].tolist() == [None, "제주시 애월읍", "제주시 삼도2동"]


def test_bus_link_statuses(tmp_path):
    df = stations(
        tmp_path,
        "1,시민회관,제주시 삼도2동,33.51,126.52\n"
        "2,시민회관,제주시 이도1동,33.51,126.53\n"
        "3,제주시청(아라방면),,33.49,126.53\n"
        "4,한라병원,제주시 연동,33.48,126.48\n"
        "5,한라병원,제주시 연동,33.48,126.48\n",
    )
    totals = pd.DataFrame(
        {
            "station_key": ["시민회관", "제주시청(아라방면)", "한라병원", "한국병원"],
            "users": [10, 20, 30, 40],
        }
    )
    linked = link_bus_usage(totals, df).set_index("station_key")
    assert linked["status"].to_dict() == {
        "시민회관": AMBIGUOUS,
        "제주시청(아라방면)": NO_ADDRESS,
        "한라병원": LINKED,
        "한국병원": NOT_FOUND,
    }
    assert pd.isna(linked.loc["시민회관", "area"])
    assert linked.loc["시민회관", "candidates"] == "제주시 삼도2동 / 제주시 이도1동"
    assert linked.loc["한라병원", "area"] == "제주시 연동"
    assert linked.loc["한라병원", "area_level"] == "행정동"


def test_bus_station_name_variants_share_key(tmp_path):
    df = stations(tmp_path, "1,제주국제공항4(대정화순일주서로),제주시 용담2동,33.5,126.49\n")
    totals = pd.DataFrame({"station_key": ["제주국제공항4(대정화순일주서로)"], "users": [5]})
    assert link_bus_usage(totals, df)["status"].tolist() == [LINKED]


def test_wifi_link_by_name_then_station_id(tmp_path):
    ap = wifi_ap(
        tmp_path,
        "함덕 서우봉 해변 #1,제주특별자치도 제주시 조천읍 함덕리\n"
        "함덕 서우봉 해변 #2,제주특별자치도 제주시 조천읍 함덕리\n"
        "제주동문시장,제주특별자치도 제주시 이도일동\n"
        "제주동문시장,제주특별자치도 제주시 일도일동\n"
        "도두봉,제주특별자치도 제주시 도두일동\n",
    )
    st = stations(tmp_path, "405000250,화북주공아파트입구,제주시 화북동,33.5,126.56\n")
    totals = pd.DataFrame(
        {
            "wifi_place_name": [
                "함덕 서우봉 해변",
                "제주동문시장",
                "도두봉",
                "버스정류소_화북주공아파트입구_(화북휴먼시아방면)_[405000250]",
                "버스정류소_없는정류소_[499999999]",
                "중앙도서관",
            ],
            "users": [1, 2, 3, 4, 5, 6],
        }
    )
    linked = link_wifi_places(totals, ap, st)
    assert linked["status"].tolist() == [
        LINKED,
        AMBIGUOUS,
        LINKED,
        LINKED,
        NOT_FOUND,
        NOT_FOUND,
    ]
    assert linked["area_level"].tolist()[:4] == ["읍면", None, "법정동", "행정동"]
    assert linked["method"].tolist()[3] == "정류소 ID"
    assert len(linked) == len(totals)


def test_match_summary_percentages():
    linked = pd.DataFrame(
        {"status": [LINKED, LINKED, AMBIGUOUS, NOT_FOUND], "users": [60, 20, 15, 5]}
    )
    s = match_summary(linked)
    assert s.loc[LINKED, "places"] == 2
    assert s.loc[LINKED, "users_pct"] == 80
    assert s.loc[NO_ADDRESS, "places"] == 0
    assert s["places_pct"].sum() == pytest.approx(100)


def test_candidate_city():
    assert candidate_city("제주시 삼도2동 / 제주시 이도1동") == "제주시"
    assert candidate_city("서귀포시 동홍동 / 제주시 연동") == "여러 시"
    assert candidate_city("") == "알 수 없음"


def test_nearest_area_reference_is_only_for_no_address(tmp_path):
    df = stations(
        tmp_path,
        "1,관덕정,제주시 삼도2동,33.5130,126.5220\n"
        "2,한라병원,제주시 연동,33.4890,126.4850\n"
        "3,주소없는정류소,,33.5125,126.5215\n",
    )
    totals = pd.DataFrame(
        {"station_key": ["관덕정", "한라병원", "주소없는정류소"], "users": [1, 1, 1]}
    )
    linked = link_bus_usage(totals, df)
    ref = nearest_area_reference(linked, df)
    assert ref.to_dict() == {2: "제주시 삼도2동"}
    assert pd.isna(linked.loc[2, "area"])
