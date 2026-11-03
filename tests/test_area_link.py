import pandas as pd
import pytest

from analytics.area_link import (
    AMBIGUOUS,
    EXCLUDE_TRAIL,
    LINKED,
    METHOD_AP_COORD,
    NO_ADDRESS,
    NOT_FOUND,
    AreaGroup,
    area_level,
    area_totals,
    assign_groups,
    candidate_city,
    link_bus_usage,
    link_wifi_places,
    load_bus_stations,
    load_wifi_ap,
    mark_exclusions,
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
    assert (
        station_id_from_wifi_name(
            "버스정류소_매일올레시장 7번입구_(동문로터리방면)_[406001804]_매일올레시장 7번입구"
        )
        == "406001804"
    )


def test_wifi_category():
    assert wifi_category("버스정류소_반석아파트[동]") == "버스정류소"
    assert wifi_category("전기차충전소_제주보건소") == "전기차충전소"
    assert wifi_category("1-93호공원") == "공원"
    assert wifi_category("17코스") == "올레·코스"
    assert wifi_category("3-B코스") == "올레·코스"
    assert wifi_category("14-1코스") == "올레·코스"
    assert wifi_category("16코스(고내포구-항파두리-광령1리)") == "올레·코스"
    assert wifi_category("서귀포매일올레시장") == "기타"
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


OLD_TOWN = AreaGroup("원도심", frozenset({"제주시 일도2동", "제주시 이도2동", "제주시 건입동"}))


def bus_linked() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "station_key": ["문예회관", "사라봉", "시민회관", "세기아파트", "한라병원", "동문시장"],
            "users": [10, 20, 30, 40, 50, 60],
            "status": [AMBIGUOUS, AMBIGUOUS, AMBIGUOUS, AMBIGUOUS, LINKED, LINKED],
            "candidates": [
                "제주시 이도2동 / 제주시 일도2동",
                "제주시 건입동 / 제주시 일도2동",
                "제주시 삼도2동 / 제주시 이도1동",
                "서귀포시 동홍동 / 제주시 연동",
                "제주시 연동",
                "제주시 일도2동",
            ],
            "area": [None, None, None, None, "제주시 연동", "제주시 일도2동"],
            "area_level": [None, None, None, None, "행정동", "행정동"],
            "method": ["정류소명"] * 6,
        }
    )


def test_cross_city_station_is_excluded():
    df = mark_exclusions(bus_linked())
    assert df.set_index("station_key")["excluded_reason"].dropna().to_dict() == {
        "세기아파트": "다른 시에 같은 이름의 정류소"
    }


def test_multi_area_trails_are_excluded_but_cross_city_rule_is_bus_only():
    wifi = pd.DataFrame(
        {
            "wifi_place_name": [
                "6코스",
                "사려니숲길",
                "제주환상자전거길",
                "화순 곶자왈 생태탐방숲길",
            ],
            "users": [5, 6, 7, 8],
            "status": [AMBIGUOUS, AMBIGUOUS, AMBIGUOUS, LINKED],
            "candidates": [
                "서귀포시 동홍동 / 서귀포시 보목동",
                "서귀포시 표선면 / 제주시 봉개동",
                "서귀포시 법환동 / 제주시 한경면",
                "서귀포시 안덕면",
            ],
            "category": ["올레·코스", "기타", "기타", "기타"],
        }
    )
    reasons = mark_exclusions(wifi)["excluded_reason"].tolist()
    assert reasons == [EXCLUDE_TRAIL] * 3 + [None]


def test_boundary_station_joins_group_when_all_candidates_inside():
    df = assign_groups(bus_linked(), [OLD_TOWN]).set_index("station_key")
    assert df.loc["문예회관", "group"] == "원도심"
    assert df.loc["문예회관", "group_method"] == "경계 묶음"
    assert df.loc["문예회관", "status"] == AMBIGUOUS
    assert df.loc["사라봉", "group"] == "원도심"
    assert pd.isna(df.loc["시민회관", "group"])  # 후보 동이 묶음 밖에 있음
    assert df.loc["동문시장", "group_method"] == "동 연결"
    assert pd.isna(df.loc["한라병원", "group"])


def test_legal_dong_ambiguity_is_not_grouped():
    wifi = bus_linked().assign(method="AP 그룹명")
    df = assign_groups(wifi, [OLD_TOWN])
    assert df.loc[df["status"] == AMBIGUOUS, "group"].isna().all()


def test_overlapping_groups_are_rejected():
    other = AreaGroup("동부", frozenset({"제주시 건입동", "제주시 화북동"}))
    with pytest.raises(ValueError, match="건입동"):
        assign_groups(bus_linked(), [OLD_TOWN, other])


def test_area_totals_skip_exclusions_and_report_them():
    df = assign_groups(mark_exclusions(bus_linked()), [OLD_TOWN])
    by_area, excluded = area_totals(df)
    assert by_area.set_index("area")["users"].to_dict() == {"제주시 일도2동": 60, "제주시 연동": 50}
    assert excluded.to_dict("records") == [
        {"excluded_reason": "다른 시에 같은 이름의 정류소", "places": 1, "users": 40}
    ]
    by_group, _ = area_totals(df, by="group")
    assert by_group.to_dict("records") == [{"group": "원도심", "places": 3, "users": 90}]


class FakeBoundaries:
    def __init__(self, by_lat: dict):
        self.by_lat = by_lat

    def locate(self, lat, lon):
        return self.by_lat.get(float(lat))


def test_dong_ap_groups_are_relinked_by_coordinates(tmp_path):
    ap = pd.DataFrame(
        {
            "apGroupName": [
                "제주동문시장 #1",
                "제주동문시장 #2",
                "도두봉",
                "탑동 #1",
                "탑동 #2",
                "함덕",
            ],
            "addressDong": [
                "제주특별자치도 제주시 이도일동",
                "제주특별자치도 제주시 일도일동",
                "제주특별자치도 제주시 도두일동",
                "제주특별자치도 제주시 삼도이동",
                "제주특별자치도 제주시 삼도이동",
                "제주특별자치도 제주시 조천읍 함덕리",
            ],
            "latitude": ["1", "1", "9", "2", "3", "4"],
            "longitude": ["0"] * 6,
        }
    )
    path = tmp_path / "ap.csv"
    ap.to_csv(path, index=False, encoding="utf-8-sig")
    ap = load_wifi_ap(path)
    b = FakeBoundaries(
        {1.0: "제주시 일도1동", 2.0: "제주시 삼도2동", 3.0: "제주시 건입동", 4.0: "제주시 구좌읍"}
    )
    totals = pd.DataFrame(
        {"wifi_place_name": ["제주동문시장", "도두봉", "탑동", "함덕"], "users": [1, 2, 3, 4]}
    )
    linked = link_wifi_places(totals, ap, stations(tmp_path, ""), b).set_index("wifi_place_name")
    # 법정동 두 곳에 걸려 애매했던 곳도 좌표가 한 행정동이면 연결
    assert linked.loc["제주동문시장", "status"] == LINKED
    assert linked.loc["제주동문시장", "area"] == "제주시 일도1동"
    assert linked.loc["제주동문시장", "area_level"] == "행정동"
    assert linked.loc["제주동문시장", "method"] == METHOD_AP_COORD
    # 좌표가 경계 밖이면 주소(법정동) 연결 유지
    assert linked.loc["도두봉", "area_level"] == "법정동"
    # AP가 여러 행정동에 떨어지면 애매함
    assert linked.loc["탑동", "status"] == AMBIGUOUS
    assert linked.loc["탑동", "candidates"] == "제주시 건입동 / 제주시 삼도2동"
    # 읍면 주소는 좌표와 달라도 주소 그대로
    assert linked.loc["함덕", "area"] == "제주시 조천읍"
