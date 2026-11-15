"""화면에 보여줄 문장·표를 만드는 함수 (Streamlit 없이 테스트할 수 있게 분리)."""

from agent.draft_contracts import CheckResult, IdeaCard

CHECK_LABELS = {
    "check_timing": "시기",
    "check_venue": "장소",
    "check_target": "대상",
    "check_risk": "위험",
    "check_budget": "규모",
}
STATUS_ICONS = {
    "pass": "✅ 통과",
    "conditional": "⚠️ 조건부",
    "fail": "❌ 실패",
    "pending": "⏳ 데이터 대기",
}
WAITING = "데이터 대기"
SEASONS = ["봄", "여름", "가을", "겨울"]
PURPOSES = ["지역 상권 활성화", "관광객 유치", "주민 참여"]

DATA_SOURCES = [
    (
        "제주데이터허브: 와이파이 장소별 방문자별 사용량·사용자 현황, 이용자유형별 버스정류소 이용인원, "
        "와이파이 AP 정보, 버스 정류소 위치"
    ),
    "제주빅데이터센터 지정 데이터: 4-11 내국인 유동인구(읍면동), 3-07·3-08·3-10 교통 (지금은 명세서 구조의 가상 데이터)",
    "기상청 기상자료개방포털 ASOS 일자료 2017~2025, 관측지점정보",
    "문화체육관광부 지역축제 개최계획 2024~2026, 전국문화축제표준데이터",
    "행정동 경계: vuski/admdongkor (CC BY 4.0)",
]


def won(krw: int | None) -> str:
    if krw is None:
        return "미정"
    if krw >= 100_000_000:
        return f"{krw / 100_000_000:,.2f}".rstrip("0").rstrip(".") + "억 원"
    return f"{krw / 10_000:,.0f}만 원"


def months_text(months: list[int]) -> str:
    return "·".join(str(m) for m in months) + "월"


def evidence_lines(card: IdeaCard) -> list[tuple[str, str, str]]:
    """카드 근거 3칸: (질문, 값 문장, 출처). pending이면 "데이터 대기"."""
    ev = card.evidence
    trend = (
        WAITING
        if ev.trend.status == "pending"
        else f"신설 {ev.trend.new_count}개, 신설 리프트 {ev.trend.new_lift}"
        + (f" ({ev.trend.verdict})" if ev.trend.verdict else "")
    )
    gap = (
        WAITING
        if ev.jeju_gap.status == "pending"
        else f"제주 같은 형식 축제 {ev.jeju_gap.jeju_count}개"
    )
    vi = ev.visitor_interest
    interest = (
        WAITING
        if vi.status == "pending" or vi.value is None
        else f"{vi.value}" + (f" ({vi.metric})" if vi.metric else "")
    )
    return [
        ("요즘 뜨는 형식인가?", trend, ev.trend.source),
        ("제주에 없는 형식인가?", gap, ev.jeju_gap.source),
        ("관광객이 좋아하는 재료인가?", interest, vi.source),
    ]


def budget_lines(card: IdeaCard) -> list[str]:
    b = card.budget
    lines = [
        f"입력 예산 {won(b.input_krw)}, 같은 형식 중간값 {won(b.format_median_krw)} → {b.scale}",
    ]
    if b.small_examples:
        lines.append(
            "작은 예산 사례: "
            + ", ".join(f"{e.name}({won(e.budget_krw)})" for e in b.small_examples)
        )
    lines.append(f"출처: {b.source}")
    return lines


def _fmt_index(index: dict | None) -> str | None:
    if not index:
        return None
    return ", ".join(f"{m}월 {v}" for m, v in index.items())


def key_numbers(r: CheckResult) -> list[str]:
    """확인 결과마다 화면에 보여줄 주요 숫자 문장."""
    e = r.evidence or {}
    out = []
    if r.check == "check_timing":
        if idx := _fmt_index(e.get("outsider_visitors_index")):
            out.append(f"외지인 방문 지수(연평균 1): {idx}")
        if e.get("weather_station"):
            out.append(f"날씨 지점: {e['weather_station']}")
        if e.get("bad_weather_months"):
            out.append(f"모든 주가 날씨 나쁜 달: {months_text(e['bad_weather_months'])}")
        if e.get("recommended_weeks"):
            out.append("추천 주: " + ", ".join(e["recommended_weeks"]))
        if e.get("overlapping_festivals"):
            out.append(
                "같은 재료 축제: "
                + ", ".join(dict.fromkeys(f["name"] for f in e["overlapping_festivals"]))
            )
    elif r.check == "check_venue":
        if e.get("low_usage_daily") is not None:
            out.append(
                f"정류소 이용 적음 기준: 하루 {e['low_usage_daily']:,.0f}명 미만, 반경 {e.get('radius_m')}m"
            )
        for key, label in (("event_hours", "행사 시간대"), ("night_return", "야간 귀가")):
            h = e.get(key) or {}
            if h.get("status") == "pending":
                out.append(f"{label} 버스: {WAITING}")
            elif h.get("stops"):
                tag = f" [{h['data_label']}]" if h.get("is_synthetic") else ""
                stops = ", ".join(
                    f"{x['stop_name']} {x['daily_boarding']:,.1f}명" for x in h["stops"]
                )
                out.append(f"{label}({h['hours']}) 하루 승차: {stops}{tag}")
    elif r.check == "check_target":
        if a := e.get("age_share"):
            out.append(
                f"대상 연령({', '.join(e['age_groups'])}) {a['dong_share_pct']}% / 제주 평균 {a['jeju_share_pct']}% ({a['ratio']}배)"
            )
        if s := e.get("sex_share"):
            out.append(
                f"성별({e['sex']}) {s['dong_share_pct']}% / 제주 평균 {s['jeju_share_pct']}% ({s['ratio']}배)"
            )
        if f := e.get("flow"):
            out.append(
                f"참고 4-11 방문인구 대상 비중 {f['dong_share_pct']}% / 제주 {f['jeju_share_pct']}% [{f.get('data_label', '')}]"
            )
    elif r.check == "check_risk":
        if e.get("same_material_festivals"):
            out.append(
                "같은 재료 축제: "
                + ", ".join(dict.fromkeys(f["name"] for f in e["same_material_festivals"]))
            )
        if res := e.get("residential"):
            for a in res["areas"]:
                out.append(
                    f"{a['admin_area']} 야간 거주인구 제주 동네 평균의 {a['ratio']}배"
                    + (" [가상 데이터]" if res["is_synthetic"] else "")
                )
        c = e.get("congestion") or {}
        if c.get("status") == "pending":
            out.append(f"정체: {WAITING}")
        elif c:
            ratio = (
                f", 가장 느린 구간 평소의 {c['min_ratio']:.0%}"
                if c.get("min_ratio") is not None
                else ""
            )
            out.append(
                f"정체: 도로 {c['links_checked']}구간 확인{ratio}"
                + (" [가상 데이터]" if c.get("is_synthetic") else "")
            )
    elif r.check == "check_budget":
        if e.get("format_median_krw") is not None:
            out.append(
                f"입력 {won(e.get('input_krw'))}, 같은 형식 중간값 {won(e['format_median_krw'])}, 하위 25% {won(e.get('format_q25_krw'))}"
            )
        if e.get("small_examples"):
            out.append(
                "비슷한 규모 사례: "
                + ", ".join(
                    f"{x['name']}({won(x['budget_krw'])}, {x['region']})"
                    for x in e["small_examples"]
                )
            )
        if e.get("visitors_estimate_text"):
            out.append(e["visitors_estimate_text"])
    return out


def venue_table(r: CheckResult) -> list[dict]:
    """check_venue 장소 후보 표 (2~3곳)."""
    rows = []
    for c in (r.evidence or {}).get("candidate_places") or []:
        rows.append(
            {
                "장소": c["name"],
                "동네": c["admin_area"],
                "위도": c["latitude"],
                "경도": c["longitude"],
                "관광 비중(%)": c["tourism_share_pct"],
                "가까운 정류소": c["stop_name"] or "없음",
                "거리(m)": c["stop_distance_m"],
                "정류소 하루 이용(명)": c["stop_daily_users"],
            }
        )
    return rows
