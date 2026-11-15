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


# ---------- 바뀐 점 (도민용 쉬운 말) ----------

FIELD_LABELS = {
    "timing.recommended_months": "추천 시기",
    "venue": "장소",
    "budget.scale": "규모",
    "programs": "프로그램",
}
WEATHER_WORDS = {"바람": "바람이 강한", "폭우": "큰비가 오는"}


def value_text(field: str, value) -> str:
    if field == "timing.recommended_months":
        return months_text(value) if value else "없음"
    if field == "venue":
        names = [
            v["name"] if isinstance(v, dict) else getattr(v, "name", str(v)) for v in value or []
        ]
        return ", ".join(names) or "미정"
    if field == "programs":
        return ", ".join(value) or "미정"
    return str(value)


def _source_check(results, change):
    """이 변경을 제안한 확인 결과."""
    same = [r for r in results if r.suggestion and r.suggestion.field == change.field
            and r.suggestion.value == change.after]  # fmt: skip
    return next((r for r in same if r.suggestion.why == change.why), same[0] if same else None)


def _month_check(result, month):
    return next(
        (m for m in (result.evidence or {}).get("month_checks", []) if m["month"] == month), None
    )


def _weather_words(month_check) -> str | None:
    kinds = {why.split()[0] for b in month_check.get("bad_weeks", []) for why in b["why"]}
    words = [WEATHER_WORDS[k] for k in ("바람", "폭우") if k in kinds]
    return " 주나 ".join(words) + " 주가 많아요" if words else None


def _timing_reason(r, change) -> tuple[str, list[str]]:
    """시기 실패 이유를 쉬운 말로. (문장, 작은 숫자들)."""
    e = r.evidence or {}
    sentences, reason_numbers, other_numbers = [], [], []  # 실패 이유가 된 숫자를 앞에
    failed = [m for m in change.before if (mc := _month_check(r, m)) and mc["status"] == "fail"]
    for m in failed:
        mc = _month_check(r, m)
        index = mc.get("outsider_visitors_index")
        low = index is not None and m in e.get("low_months", [])
        weather = _weather_words(mc) if not mc.get("good_weeks") else None
        if low and weather:
            sentences.append(f"{m}월은 관광객이 평소보다 적고 {weather}.")
        elif low:
            sentences.append(f"{m}월은 관광객이 평소보다 적어요.")
        elif weather:
            sentences.append(f"{m}월은 {weather}.")
        if index is not None:
            text = f"{m}월 관광객 지표 {index} (1이 연평균, 와이파이 관광 사용량 기준)"
            (reason_numbers if low else other_numbers).append(text)
        if weather:  # 날씨가 실패 이유일 때만
            total = len(mc["bad_weeks"]) + len(mc.get("good_weeks", []))
            ratios = [w for b in mc["bad_weeks"] for w in b["why"]]
            reason_numbers.append(
                f"{m}월 날씨 나쁜 주 {len(mc['bad_weeks'])}/{total}주 ({'; '.join(ratios[:2])})"
            )
    return (
        " ".join(sentences) or "추천 시기에 맞지 않는 달이 있어요.",
        reason_numbers + other_numbers,
    )


def _target_reason(r, change) -> tuple[str, list[str]]:
    e = r.evidence or {}
    who = e.get("target") or "대상"
    months = months_text(change.before)
    numbers = []
    if a := e.get("age_share"):
        numbers.append(
            f"대상 비중 {a['dong_share_pct']}% (제주 평균 {a['jeju_share_pct']}%, 와이파이 사용자 기준)"
        )
    return (
        f"{months}에는 이 동네에 '{who}' 방문이 제주 평균보다 적어서, 더 많이 찾는 달로 바꿨어요.",
        numbers,
    )


def _budget_reason(r, change) -> tuple[str, list[str]]:
    e = r.evidence or {}
    numbers = []
    if e.get("format_median_krw") is not None:
        numbers.append(
            f"입력 예산 {won(e.get('input_krw'))}, 같은 형식 축제 예산 중간값 {won(e['format_median_krw'])}"
        )
    return "가진 예산으로 연 같은 형식 축제 사례가 없어서, 규모를 줄인 버전으로 바꿨어요.", numbers


def _venue_reason(r, change) -> tuple[str, list[str]]:
    region = (r.evidence or {}).get("region") or "이 지역"
    return f"{region} 안에서 관광객이 모이는 장소를 찾지 못해, 이웃 동네 장소로 바꿨어요.", []


REASONS = {
    "check_timing": _timing_reason,
    "check_target": _target_reason,
    "check_budget": _budget_reason,
    "check_venue": _venue_reason,
}


def _after_note(next_results, change) -> str | None:
    """바꾼 달이 통과가 아니라 조건부면 솔직하게 알린다."""
    if change.field != "timing.recommended_months" or not next_results:
        return None
    timing = next((r for r in next_results if r.check == "check_timing"), None)
    if timing is None:
        return None
    e = timing.evidence or {}
    in_season = "제철 안에서 " if e.get("material_season") else ""
    notes = []
    for m in change.after:
        mc = _month_check(timing, m)
        if not mc or mc["status"] != "conditional":
            continue
        if m in e.get("slightly_low_months", []):
            notes.append(f"{m}월은 평소보다 관광객이 약간 적지만, {in_season}가장 나은 달이에요.")
        elif mc.get("overlapping_festivals"):
            notes.append(
                f"{m}월에는 같은 재료 축제가 있지만, {in_season}가장 나은 달이에요. 날짜가 겹치지 않게 잡아 주세요."
            )
    return " ".join(notes) or None


LOW_DATA_NOTICE = "이 지역은 자료가 적어 결과가 불안정할 수 있어요"


def low_data_notes(results) -> list[str]:
    """확인 결과 evidence의 low_data(자료가 적은 이유)를 모은다."""
    notes = []
    for r in results:
        for note in (r.evidence or {}).get("low_data") or []:
            if note not in notes:
                notes.append(note)
    return notes


def friendly_changes(run) -> list[dict]:
    """화면용 바뀐 점: title, reason, numbers(작게), note(조건부일 때), season."""
    out = []
    rounds = run.rounds
    for i, rd in enumerate(rounds):
        nxt = rounds[i + 1].results if i + 1 < len(rounds) else None
        for change in rd.changes:
            r = _source_check(rd.results, change)
            if r is not None and r.check in REASONS:
                reason, numbers = REASONS[r.check](r, change)
            else:
                reason, numbers = change.why, []
            season = None
            if change.field == "timing.recommended_months":
                timing = next((x for x in rd.results if x.check == "check_timing"), None)
                ms = ((timing.evidence or {}).get("material_season") or {}) if timing else {}
                if ms.get("months"):
                    season = f"제철: {months_text(ms['months'])}"  # 근거 문구는 보여주지 않는다
            title = (
                f"{FIELD_LABELS.get(change.field, change.field)}: "
                f"{value_text(change.field, change.before)} → {value_text(change.field, change.after)}"
            )
            if out and out[-1]["title"] == title and out[-1]["round"] == rd.round:
                out[-1]["reason"] += " " + reason  # 같은 변경을 두 확인이 제안하면 한 칸에
                out[-1]["numbers"] += numbers
                if r is not None:
                    out[-1]["low_data"] += [
                        n for n in low_data_notes([r]) if n not in out[-1]["low_data"]
                    ]
                continue
            out.append(
                {
                    "round": rd.round,
                    "title": title,
                    "reason": reason,
                    "numbers": numbers,
                    "note": _after_note(nxt, change),
                    "season": season,
                    "low_data": low_data_notes([r]) if r is not None else [],
                }
            )
    return out
