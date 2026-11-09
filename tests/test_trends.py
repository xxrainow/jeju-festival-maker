import pandas as pd
import pytest

from research.designation import DESIGNATION, attach_designation, match_designation
from research.trends import (
    PANEL_PATH,
    add_tags,
    jeju_festivals_by_month,
    jeju_gap,
    link_panel,
    load_panel,
    norm_name,
    standardize,
    tag_budgets,
    tag_trends,
)


def raw_year(year: int, rows: list[tuple]) -> pd.DataFrame:
    """(시도, 기초, 축제명, 최초개최연도, 예산(백만 원), 월) → load_mcst가 만드는 칸 구성."""
    d = pd.DataFrame(rows, columns=["시도", "기초", "축제명", "최초개최연도", "예산", "월"])
    d.insert(0, "연번", range(1, len(d) + 1))
    d["유형_raw"] = "1. 문화예술"
    d["장소유형"] = "nan"
    d["개최주기"] = "1. 매년"
    d["방문객"] = 1000
    d["방문객_내"] = d["방문객_외"] = None
    return standardize(d, year)


def test_norm_name_drops_year_round_and_suffix():
    assert norm_name("제12회 2026 애월 감귤축제(가을)") == "애월감귤"
    assert norm_name("2025 서귀포 야시장 페스티벌") == "서귀포야시장"


def test_standardize_strips_codes_and_drops_empty_rows():
    d = raw_year(2026, [("1. 제주", "nan", "애월 감귤마켓", 2024, "1,200", 11)])
    d = pd.concat([d, raw_year(2026, [("제주", "-", None, 2024, 1, 1)])])
    assert d["시도"].tolist() == ["제주"]
    assert d["기초"].tolist() == ["-"]
    assert d["예산"].tolist() == [1200.0]
    assert d["장소유형"].isna().all()


def test_link_panel_joins_same_festival_across_years():
    y24 = raw_year(2024, [("제주", "-", "제1회 애월 감귤마켓", 2023, 10, 11)])
    y25 = raw_year(2025, [("제주", "-", "제2회 애월감귤마켓", 2023, 10, 11)])
    y26 = raw_year(2026, [("제주", "-", "2026 애월 감귤 마켓 축제", 2023, 10, 11),
                          ("제주", "-", "성산 일출축제", 2010, 50, 1)])  # fmt: skip
    panel = link_panel([y24, y25, y26])
    fids = panel.groupby("fid")["연도"].nunique()
    assert sorted(fids.tolist()) == [1, 3]


def test_add_tags_marks_format_and_material():
    df = add_tags(pd.DataFrame({"축제명": ["서귀포 방어 야시장", "한라산 눈꽃축제"]}))
    assert df.loc[0, "시장·상권"] and df.loc[0, "수산물"] and not df.loc[0, "겨울 레저"]
    assert df.loc[1, "겨울 레저"]


def test_tag_trends_lift_and_verdict():
    old = [("서울", f"구{i}", f"전통문화제{i}", 2000, 10, 5) for i in range(20)]
    new = [("부산", f"구{i}", f"골목시장 마켓{i}", 2024, 10, 5) for i in range(12)]
    panel = link_panel([raw_year(2024, old), raw_year(2025, old), raw_year(2026, old + new)])
    out = tag_trends(panel, min_n=1)
    assert out.loc["시장·상권", "신설수"] == 12
    assert out.loc["시장·상권", "판정"] == "확실한 상승"
    assert out.loc["문화제·예술제", "판정"] == "성숙·감소"


def test_jeju_gap_month_and_budget():
    rows = [("제주", "-", "모슬포 방어축제", 2001, 300, 11), ("제주", "-", "유채꽃축제", 1990, 500, 3),
            ("서울", "-", "망원시장 축제", 2024, 5, 10), ("서울", "-", "한강 마켓", 2024, 20, 10)]  # fmt: skip
    panel = link_panel([raw_year(2026, rows)])
    gap = jeju_gap(panel)
    assert gap.loc["수산물", "제주건수"] == 1
    assert gap.loc["시장·상권", "제주건수"] == 0
    assert gap.attrs["제주축제수"] == 2
    months = jeju_festivals_by_month(panel)
    assert months[11] == 1 and months[3] == 1 and months[10] == 0
    budgets = tag_budgets(panel)["시장·상권"]
    assert budgets["예산_원"].tolist() == [5_000_000, 20_000_000]


def test_match_designation_finds_renamed_festival():
    rows = [("강원", "강릉시", "제18회 강릉커피축제", 2009, 500, 10),
            ("제주", "-", "탐라문화제", 1962, 900, 10)]  # fmt: skip
    panel = link_panel([raw_year(2026, rows)])
    matches = match_designation(panel)
    # 27 + 20 + 20 = 67이지만 부천국제만화제·음성품바축제가 예비(2026)·문화관광(2027)이라 65개
    assert len(matches) == len(DESIGNATION) == 65
    hit = matches[matches["지정명"] == "강릉커피축제"].iloc[0]
    assert hit["매칭"].startswith("정확")
    out = attach_designation(panel, matches)
    assert out.loc[out["축제명"].str.contains("강릉"), "지정_2026"].item() == "문화관광"
    assert out.loc[out["축제명"].str.contains("탐라"), "지정_2026"].isna().all()


@pytest.mark.skipif(not PANEL_PATH.exists(), reason="실데이터 패널 없음 (research.trends로 생성)")
def test_real_panel_matches_design_document():
    """설계 기획서 2·3·9절 숫자가 그대로 나오는지 확인 (문체부 실데이터)."""
    panel = load_panel()
    assert panel.groupby("연도").size().tolist() == [1170, 1214, 1266]
    assert (panel.groupby("fid")["연도"].nunique() == 3).sum() == 660
    trends = tag_trends(panel)
    assert trends.loc["시장·상권", "신설수"] == 16
    assert trends.loc["시장·상권", "신설리프트"] == 3.6
    assert trends.loc["수산물", "판정"] == "성숙·감소"
    assert jeju_gap(panel).loc["수산물", "제주건수"] == 8
    assert tag_budgets(panel)["시장·상권"]["예산_원"].median() == 60_000_000
    assert match_designation(panel)["fid"].notna().sum() == 65
