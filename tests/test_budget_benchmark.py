import pandas as pd

from analytics.budget_benchmark import distribution, eligible, link_jeju, outlier_comparison


def plan(**cols) -> pd.DataFrame:
    n = len(next(iter(cols.values())))
    base = {
        "festival_type": ["문화예술"] * n,
        "place_type": ["녹지형"] * n,
        "duration_class": ["2~3일"] * n,
        "budget_total": [100.0] * n,
        "per_capita_krw": [None] * n,
        "per_capita_outlier": [False] * n,
    }
    return pd.DataFrame({**base, **cols})


def test_eligible_drops_missing_budget_undecided_place_and_period():
    df = plan(
        budget_total=[100.0, None, 50.0, 70.0],
        place_type=["녹지형", "녹지형", "미정", "녹지형"],
        duration_class=["2~3일", "2~3일", "2~3일", "미정"],
    )
    rows, excluded = eligible(df)
    assert len(rows) == 1
    assert dict(zip(excluded["뺀 사유"], excluded["건수"])) == {
        "예산 결측": 1,
        "장소 유형 미정": 1,
        "기간 미정": 1,
    }


def test_distribution_quartiles_and_small_sample():
    df = plan(
        budget_total=[10.0, 20.0, 30.0, 40.0, 50.0, 99.0],
        place_type=["녹지형"] * 5 + ["수변형"],
    )
    out = distribution(df, ["festival_type", "place_type"]).set_index("place_type")
    assert out.loc["녹지형", "median"] == 30
    assert out.loc["녹지형", "q25"] == 20 and out.loc["녹지형", "q75"] == 40
    assert out.loc["녹지형", "sample_note"] == ""
    assert out.loc["수변형", "sample_note"] == "표본 부족"


def test_outlier_comparison():
    df = plan(
        budget_total=[100.0, 200.0, 300.0],
        per_capita_krw=[400.0, 5000.0, 6000.0],
        per_capita_outlier=[True, False, False],
    )
    row = outlier_comparison(df).iloc[0]
    assert row["예산 중간값 (포함)"] == 200 and row["예산 중간값 (제외)"] == 250
    assert row["1인당 비용 건수 (포함)"] == 3 and row["1인당 비용 건수 (제외)"] == 2


def test_link_jeju():
    df = pd.DataFrame(
        {
            "sido": ["제주"] * 6 + ["서울"],
            "place_sigungu": [
                "제주시",
                "서귀포시",
                "제주시",
                "서귀포시",
                "제주시",
                "제주시",
                "중구",
            ],
            "place_emd": ["애월읍", "천지동", "용강동", "서귀동", "-", "-", "필동"],
            "place_name": [
                "새별오름",
                "천지연",
                "목장",
                "서귀포항",
                "도내일원",
                "서귀포농업기술센터",
                "-",
            ],
        }
    )
    mapping = pd.DataFrame(
        {
            "legal_dong": [
                "제주시 용강동",
                "서귀포시 서귀동",
                "서귀포시 서귀동",
                "서귀포시 천지동",
            ],
            "admin_dong": [
                "제주시 봉개동",
                "서귀포시 천지동",
                "서귀포시 송산동",
                "서귀포시 천지동",
            ],
            "used": [True, True, True, True],
            "evidence": ["보통"] * 4,
        }
    )
    out = link_jeju(df, mapping)
    assert len(out) == 6
    assert out["link_result"].tolist() == [
        "읍면",
        "행정동 이름 일치",
        "법정동 → 1:1 변환",
        "법정동 → 여러 행정동",
        "여러 곳 (읍면동 없음)",
        "읍면동 없음",
    ]
    assert out["admin_area"].tolist()[:3] == ["제주시 애월읍", "서귀포시 천지동", "제주시 봉개동"]
    assert out["admin_area"].iloc[3:].isna().all()
    assert out["place_check"].iloc[1] == "법정동 이름이기도 함 (확인 필요)"
    assert out["place_check"].iloc[5] == "시군구와 장소명의 시가 다름"


def test_per_capita_summary_side_by_side():
    from analytics.budget_benchmark import per_capita_summary

    df = plan(
        per_capita_krw=[1000.0, 3000.0, None],
        per_capita_telecom_krw=[None, None, 500.0],
    )
    row = per_capita_summary(df).iloc[0]
    assert row["계측 건수"] == 2 and row["계측 중간값"] == 2000
    assert row["통신 데이터 건수"] == 1 and row["통신 데이터 중간값"] == 500


def test_match_standard_by_name():
    from analytics.budget_benchmark import festival_key, match_standard

    assert festival_key("2026 제21회 중문칠선녀축제") == "중문칠선녀축제"
    standard = pd.DataFrame(
        {
            "std_name": [
                "제21회 중문칠선녀축제",
                "네 번째. 서홍동 웃물교 벚꽃구경",
                "가을국화축제 체험",
                "가을국화축제 공연",
            ],
            "std_admin_area": ["서귀포시 중문동", None, "가", "나"],
        }
    )
    names = pd.Series(
        ["2026 제21회 중문칠선녀축제", "네 번째 서홍동 웃물교 벚꽃구경", "가을국화축제", "없음"]
    )
    out = match_standard(names, standard)
    assert out["std_name"].tolist()[:2] == [
        "제21회 중문칠선녀축제",
        "네 번째. 서홍동 웃물교 벚꽃구경",
    ]
    assert out["std_name"].iloc[2:].isna().all()  # 여러 개가 맞거나 없으면 매칭 안 함


def test_link_jeju_uses_standard_coordinates():
    df = pd.DataFrame(
        {
            "sido": ["제주"] * 4,
            "name": ["칠십리축제", "칠선녀축제", "다른동축제", "웃물교벚꽃"],
            "place_sigungu": ["서귀포시"] * 4,
            "place_emd": ["-", "중문동", "서홍동", "서홍동"],
            "place_name": ["천지연폭포 주차장", "천제연", "솜반천", "웃물교"],
        }
    )
    mapping = pd.DataFrame(
        {
            "legal_dong": ["서귀포시 중문동", "서귀포시 서홍동"],
            "admin_dong": ["서귀포시 중문동", "서귀포시 천지동"],
            "used": [True, True],
            "evidence": ["보통", "보통"],
        }
    )
    standard = pd.DataFrame(
        {
            "std_name": ["칠십리축제", "칠선녀축제", "다른동축제", "웃물교벚꽃"],
            "std_admin_area": ["서귀포시 천지동", "서귀포시 중문동", "서귀포시 천지동", None],
        }
    )
    out = link_jeju(df, mapping, standard).set_index("name")
    assert out.loc["칠십리축제", "link_result"] == "표준데이터 좌표"
    assert out.loc["칠십리축제", "admin_area"] == "서귀포시 천지동"
    assert out.loc["칠선녀축제", "place_check"] == "표준데이터 좌표로 확인 (같음)"
    assert out.loc["다른동축제", "place_check"] == "표준데이터 좌표는 서귀포시 천지동 (다름)"
    assert out.loc["다른동축제", "admin_area"] == "서귀포시 서홍동"  # 바꾸지 않고 표시만
    assert out.loc["웃물교벚꽃", "place_check"] == "법정동 이름이기도 함 (표준데이터에 좌표 없음)"
