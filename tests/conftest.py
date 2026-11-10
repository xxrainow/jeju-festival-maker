import pytest

from agent.idea_gen import FORMATS, FormatStats, TrendData


@pytest.fixture
def trend_data() -> TrendData:
    """문체부 원자료 없이 쓰는 작은 트렌드 숫자 묶음 (실데이터 값을 일부 본뜬 가짜)."""
    lifts = {
        "여름·물놀이": (16, 4.23, 1), "시장·상권": (16, 3.6, 0), "정원·가드닝": (10, 2.95, 0),
        "푸드·디저트": (22, 2.82, 0), "맥주·주류": (13, 2.41, 0), "도심·거리·골목": (14, 2.19, 0),
        "야간·빛·드론": (31, 1.84, 0), "영화·책·아트": (13, 1.77, 0),
    }  # fmt: skip
    formats = {}
    for fmt in FORMATS:
        new, lift, jeju = lifts[fmt]
        formats[fmt] = FormatStats(
            new_count=new,
            new_lift=lift,
            verdict="확실한 상승",
            jeju_count=jeju,
            budgets_krw=(
                ("작은 마켓", 5_000_000),
                ("중간 마켓", 60_000_000),
                ("큰 마켓", 90_000_000),
            ),
            designated=(("강릉커피축제", "문화관광"),) if fmt == "푸드·디저트" else (),
        )
    month_counts = {m: 0 for m in range(1, 13)} | {10: 13, 12: 1, 3: 5, 1: 0, 6: 1}
    return TrendData(
        formats=formats,
        strength={"농축산 특산": 1.18, "수산물": 3.35, "봄꽃": 1.68},
        jeju_by_month=month_counts,
    )
