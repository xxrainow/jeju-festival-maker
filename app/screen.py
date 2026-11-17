"""화면에 보여줄 문장·표를 만드는 함수 (Streamlit 없이 테스트할 수 있게 분리)."""

import re

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


def blocked_check_guidance(run) -> list[str]:
    """선택한 안의 마지막 검사에서 실패한 항목과 수정 방법만 설명한다."""
    lines = []
    for result in run.rounds[-1].results:
        if result.status != "fail":
            continue
        lines.append(f"**{CHECK_LABELS[result.check]} — {result.reason}**")
        evidence = result.evidence or {}
        if result.check == "check_timing":
            from analytics.check_timing import LOW_INDEX

            indices = evidence.get("outsider_visitors_index") or {}
            low = evidence.get("low_months") or []
            if low and isinstance(indices, dict):
                values = []
                for month in low:
                    value = indices.get(month, indices.get(str(month)))
                    if isinstance(value, (int, float)):
                        values.append(f"{month}월 약 {value * 100:.0f}%")
                if values:
                    lines.append(
                        "관광 목적 와이파이 사용량을 연평균과 비교한 값이에요: "
                        + ", ".join(values)
                        + f". 현재 앱은 연평균의 {LOW_INDEX * 100:.0f}% 미만이면 "
                        "시기 확인을 통과시키지 않아요. 실제 관광객 수나 개최 금지를 뜻하지는 않아요."
                    )
            failed_months = [
                c["month"] for c in evidence.get("month_checks", []) if c["status"] == "fail"
            ]
            if failed_months:
                lines.append(
                    "여러 달을 고르면 모두 확인해요. 선택한 "
                    + "·".join(f"{m}월" for m in failed_months)
                    + "이 통과하지 못해 이 안으로는 아직 진행할 수 없어요."
                )
        suggestion = result.suggestion
        if suggestion and suggestion.field == "timing.recommended_months":
            lines.append(
                "**이렇게 바꿔보세요:** 개최 월을 "
                + "·".join(f"{m}월" for m in suggestion.value)
                + "로 바꾸고 ‘이 조건으로 다시 확인’을 눌러주세요. "
                "직접 고친 안은 자동으로 변경하지 않아요."
            )
        elif suggestion:
            lines.append("**수정 제안:** " + suggestion.why)
        else:
            lines.append(
                "자동으로 제안할 대안이 없어요. 위 근거를 확인해 조건을 조정하거나 "
                "다른 아이디어를 골라주세요."
            )
    return lines


def md(text):
    """화면 출력용: Streamlit 마크다운에서 "~"가 두 번 나오면 취소선이 되므로 "\\~"로 바꾼다.

    이미 "\\~"인 곳은 그대로 둔다. 문자열이 아니면 그대로 돌려준다 (표 값 등은 쓰지 않는다).
    """
    if not isinstance(text, str):
        return text
    return re.sub(r"(?<!\\)~", r"\\~", text)


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


def ordered_months(months: list[int]) -> list[int]:
    """이어지는 순서로: [1, 2, 11, 12] → [11, 12, 1, 2]. 가장 크게 비는 곳 다음 달부터 센다."""
    ms = sorted(set(months))
    if len(ms) < 2:
        return ms
    gaps = [((ms[(i + 1) % len(ms)] - m) % 12, i) for i, m in enumerate(ms)]
    _, i = max(gaps, key=lambda g: g[0])  # 같으면 앞쪽 (연초부터)
    start = (i + 1) % len(ms)
    return ms[start:] + ms[:start]


def months_text(months: list[int]) -> str:
    return "·".join(str(m) for m in ordered_months(months)) + "월"


VERDICT_TITLES = {
    "확실한 상승": "요즘 늘고 있는 축제예요 📈",
    "관찰 대상": "조금씩 늘고 있는 축제예요",
    "정체": "꾸준히 열리는 축제예요",
    "성숙·감소": "이미 많이 열리는 축제예요",
}
NEW_FROM_YEAR = (
    2023  # research.trends.tag_trends(new_from=2023): 2023년 이후 처음 연 축제가 "새로 생긴 축제"
)


def _has_final(word: str) -> bool:
    """마지막 글자에 받침이 있는지 (조사 고르기)."""
    ch = word.strip()[-1:]
    return bool(ch) and "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 != 0


def josa(word: str, with_final: str, without_final: str) -> str:
    return word + (with_final if _has_final(word) else without_final)


def plain_source(src: str | None) -> str:
    """출처 줄임말을 기관 이름으로 풀어 쓴다. 예: "문체부 지역축제 2024-2026" → "문화체육관광부 지역축제 개최계획 (2024~2026)"."""
    if not src:
        return ""
    if m := re.fullmatch(r"제주 축제 목록 \((.*)\)", src.strip()):
        return f"{plain_source(m.group(1))} 중 제주 축제"
    # 괄호 안에서는 괄호를 겹치지 않게 연도만 붙인다
    out = re.sub(
        r"(\([^)]*?)문체부 지역축제 (\d{4})\s*[-~]\s*(\d{4})",
        r"\1문화체육관광부 지역축제 개최계획 \2~\3",
        src,
    )
    out = re.sub(
        r"(\([^)]*?)문체부 지역축제 (\d{4})", r"\1문화체육관광부 지역축제 개최계획 \2", out
    )
    out = re.sub(
        r"문체부 지역축제 (\d{4})\s*[-~]\s*(\d{4})",
        r"문화체육관광부 지역축제 개최계획 (\1~\2)",
        out,
    )
    out = re.sub(r"문체부 지역축제 (\d{4})", r"문화체육관광부 지역축제 개최계획 (\1)", out)
    out = out.replace("문체부", "문화체육관광부")
    out = out.replace("와이파이 AP별 이용 현황", "제주데이터허브 와이파이 이용 현황")
    if out.startswith("와이파이 장소별"):
        out = "제주데이터허브 " + out
    return out


_UNSET = object()


# 카드 visitor_interest.metric에 이 말이 있으면 "축제 동네" 기준 (agent.idea_gen.INTEREST_METRICS)
FESTIVAL_AREA_MARK = "축제가 열리는 동네"


def jeju_tourist_share() -> float | None:
    """제주 전체 장소의 관광 목적 와이파이 사용량 비중(%) = A의 소재 사전 base_tourist_share_pct.

    가공본 CSV에는 따로 없어서 재료별 tourist_share_pct ÷ tourist_vs_avg로 되살린다 (재료마다 같은 값).
    """
    import pandas as pd

    from research.materials import PUBLISHED_MATERIALS_PATH

    try:
        d = pd.read_csv(PUBLISHED_MATERIALS_PATH)
    except FileNotFoundError:
        return None
    x = d.dropna(subset=["tourist_share_pct", "tourist_vs_avg"])
    x = x[x["tourist_vs_avg"] > 0]
    if x.empty:
        return None
    return round(float((x["tourist_share_pct"] / x["tourist_vs_avg"]).median()), 1)


def evidence_lines(card: IdeaCard, jeju_avg=_UNSET) -> list[tuple[str, str, str]]:
    """카드 근거 3칸을 쉬운 말로: (제목, 본문, 출처). 확인 중이면 "아직 확인 중이에요"."""
    ev = card.evidence
    t = ev.trend
    if t.status == "pending" or t.new_count is None:
        trend = ("요즘 뜨는 축제인지 아직 확인 중이에요", "")
    else:
        verdict = next(
            (v for k, v in VERDICT_TITLES.items() if t.verdict and t.verdict.startswith(k)), None
        )
        # new_count: 2026년 계획에 있는 축제 중 2023년 이후 처음 연 축제 수 (research.trends.tag_trends)
        body = f"{NEW_FROM_YEAR}년 이후 새로 생겨 2026년에 열리는 {card.format} 축제가 전국 {t.new_count}개예요."
        if t.new_lift is not None:
            lift = round(t.new_lift, 1)
            body += (
                f" 새로 생긴 축제 중 이 형식의 비율이 예전부터 열던 축제보다 {lift}배 높아요."
                if lift >= 1
                else f" 새로 생긴 축제 중 이 형식의 비율은 예전부터 열던 축제의 {lift}배로 더 낮아요."
            )
        trend = (verdict or "전국 축제 흐름", body)
    g = ev.jeju_gap
    if g.status == "pending" or g.jeju_count is None:
        gap = ("제주에 같은 축제가 있는지 아직 확인 중이에요", "")
    elif g.jeju_count == 0:
        gap = ("제주에는 아직 없어요", f"제주에서 열리는 {card.format} 축제가 없어요.")
    else:
        gap = (f"제주에도 {g.jeju_count}개 있어요", f"제주에서 이미 열리는 {card.format} 축제예요.")
    vi = ev.visitor_interest
    if vi.status == "pending" or vi.value is None:
        interest = ("관광객 관심은 아직 확인 중이에요", "")
    else:
        # 와이파이는 사람 수가 아니라 데이터 사용량이다. 제주 전체 평균 관광 비중과 비교한다
        avg = jeju_tourist_share() if jeju_avg is _UNSET else jeju_avg
        # 기준이 둘이다 (A의 소재 사전 interest_basis, 카드에는 visitor_interest.metric으로 온다)
        # - 장소 이름: 재료 이름이 든 와이파이 장소 (예: 한담해변 → 해변)
        # - 축제 동네: 그런 장소가 없어 같은 재료 기존 축제가 열리는 동네 전체로 대신 잰 값 (예: 방어 → 대정읍)
        by_festival_area = FESTIVAL_AREA_MARK in (vi.metric or "")
        if by_festival_area:
            subject = f"{card.material} 축제가 열리는 동네"
            body = f"{subject}의 와이파이 사용량 중 관광 목적이 {vi.value:.0f}%예요"
            note = f" {card.material} 자체가 아니라 동네 전체 기준이에요."
        else:
            subject = f"{card.material} 관련 장소"
            body = f"{card.material} 관련 제주 장소의 와이파이 사용량 중 관광 목적이 {vi.value:.0f}%예요"
            note = ""
        if avg is None:
            interest = ("관광객 관심", body + "." + note)
        else:
            if vi.value >= avg:
                title = (
                    f"{subject}는 관광객이 많이 찾아요"
                    if by_festival_area
                    else f"관광객이 많이 찾는 {josa(card.material, '이에요', '예요')}"
                )
            else:
                # 관광 외 사용량에는 거주뿐 아니라 업무·기타도 섞여 있어 "주민"이라고 하지 않는다
                title = f"{subject}는 관광보다 생활·업무 이용이 많아요"
            interest = (title, body + f" (제주 평균 {avg:.0f}%)." + note)
    return [
        (*trend, plain_source(t.source)),
        (*gap, plain_source(g.source)),
        (*interest, plain_source(vi.source)),
    ]


def idea_summary(card: IdeaCard) -> list[tuple[str, str, str]]:
    """목록에서는 비교에 필요한 수치만 보여주고, 자세한 근거는 패널에서 읽는다."""
    trend = card.evidence.trend
    if trend.status == "pending" or trend.new_count is None:
        trend_text = "아직 확인 중"
    else:
        trend_text = f"전국 새 축제 {trend.new_count}개"
        if trend.new_lift is not None:
            trend_text += f" · 신설 비율 {trend.new_lift:.1f}배"
    gap = card.evidence.jeju_gap
    gap_text = (
        "아직 확인 중"
        if gap.status == "pending" or gap.jeju_count is None
        else f"같은 형식 축제 {gap.jeju_count}개"
    )
    budget = card.budget
    if budget.format_median_krw is None:
        budget_text = "비교 예산 확인 중"
    elif budget.input_krw is None:
        budget_text = f"비슷한 축제 보통 {won(budget.format_median_krw)}"
    else:
        scale = "작게 여는 안" if budget.scale == "소규모 버전" else "기본 규모"
        budget_text = f"{won(budget.input_krw)} · {scale}"
    return [
        ("전국 트렌드", trend_text, "데이터 대기" if trend_text == "아직 확인 중" else "사실"),
        ("제주 현황", gap_text, "데이터 대기" if gap_text == "아직 확인 중" else "사실"),
        ("예산", budget_text, "데이터 대기" if budget.format_median_krw is None
         else "에이전트 해석" if budget.input_krw is not None else "사실"),
    ]


def reference_text(card: IdeaCard) -> str:
    ref = card.reference
    if ref.type == "선점 기회" or not ref.designated_festivals:
        return "아직 전국에 대표 축제가 없어요. 먼저 시작할 기회예요"
    return "비슷한 성공 축제: " + ", ".join(f.name for f in ref.designated_festivals)


def timing_text(card: IdeaCard) -> str:
    months = card.timing.recommended_months
    text = f"추천 시기: {months_text(months)}"
    fest = card.timing.jeju_festivals_in_month
    if fest is not None:
        text += f" · {'이 달' if len(months) == 1 else '이 시기'} 제주 축제 {fest}개"
    return text


def budget_lines(card: IdeaCard) -> list[str]:
    """예산을 쉬운 말로. 마지막 줄은 출처."""
    b = card.budget
    median, given = b.format_median_krw, b.input_krw
    if median is None:
        lines = ["비슷한 축제 예산은 아직 확인 중이에요."]
    elif given is None:
        lines = [
            f"비슷한 축제는 보통 {josa(won(median), '이', '가')} 들어요. 예산을 정하면 규모를 맞춰 드릴게요."
        ]
    elif b.scale == "소규모 버전":
        lines = [
            (
                f"비슷한 축제는 보통 {josa(won(median), '이', '가')} 들어요. "
                f"입력한 {josa(won(given), '으로는', '로는')} 작게 여는 걸 추천해요."
            )
        ]
    else:
        lines = [
            f"입력한 {josa(won(given), '이면', '면')} 비슷한 축제(보통 {won(median)})만큼 열 수 있어요."
        ]
    if b.small_examples:
        lines.append(
            "작은 예산으로 연 축제: "
            + ", ".join(f"{e.name}({won(e.budget_krw)})" for e in b.small_examples)
        )
    lines.append(f"출처: {plain_source(b.source)}")
    return lines


def _jamo(ch: str) -> tuple[int, int, int]:
    code = ord(ch) - 0xAC00
    return code // 588, (code % 588) // 28, code % 28


def _syllable(cho: int, jung: int, jong: int) -> str:
    return chr(0xAC00 + cho * 588 + jung * 28 + jong)


def check_phrase(hypothesis: str) -> str:
    """가설 문장 끝 "~다"를 "~인지"로. 예: "관광객이 충분하다" → "관광객이 충분한지".

    규칙에 맞지 않으면 원문 그대로 둔다 (LLM 문장은 모양이 다양하다).
    """
    h = hypothesis.strip().rstrip(".")
    if not h.endswith("다") or len(h) < 2:
        return hypothesis.strip()
    stem, last = h[:-1], h[-2]
    if not ("가" <= last <= "힣"):
        return hypothesis.strip()
    if stem.endswith(("있", "없")):
        return stem + "는지"
    if stem.endswith("는"):  # 않는다, 막는다 → 않는지, 막는지
        return stem[:-1] + "는지"
    cho, jung, jong = _jamo(last)
    if jong == 4:  # 간다, 온다, 참여한다 → 가는지, 오는지, 참여하는지
        return stem[:-1] + _syllable(cho, jung, 0) + "는지"
    if jong == 0:  # 충분하다 → 충분한지, 크다 → 큰지
        return stem[:-1] + _syllable(cho, jung, 4) + "지"
    return stem + "은지"  # 많다 → 많은지


def _fmt_index(index: dict | None) -> str | None:
    if not index:
        return None
    return ", ".join(f"{m}월 {v}" for m, v in index.items())


SYNTHETIC_TAG = " (가상 데이터)"  # 화면의 가상 데이터 표시는 모두 이 모양


def festival_place(f: dict) -> str:
    """같은 재료 축제의 장소·거리: "서귀포시 대정읍, 같은 동네", "서귀포시 서홍동, 약 6km", "장소 미확인"."""
    area, relation, km = f.get("admin_area"), f.get("relation"), f.get("distance_km")
    if not area:
        return "장소 미확인"
    if relation == "같은 동네":
        return f"{area}, 같은 동네"
    if km is not None:
        return f"{area}, 약 {km:.1f}km"  # 10km 기준과 맞게 소수 첫째 자리까지
    return area


def festivals_text(festivals: list[dict]) -> str:
    """ "제26회 최남단 방어 축제(11월, 서귀포시 대정읍, 같은 동네)" 목록. 같은 축제·같은 달은 한 번만."""
    seen = {}
    for f in festivals:
        where = festival_place(f)
        label = f"{f['month']}월, {where}" if f.get("month") else where
        seen.setdefault((f["name"], f.get("month")), f"{f['name']}({label})")
    return ", ".join(seen.values())


def near_festival_sentence(month: int, festivals: list[dict]) -> str:
    """바뀐 점: 같은 동네·10km 이내 같은 재료 축제 때문에 뺀 달의 이유."""
    parts = []
    for f in festivals:
        if f.get("relation") == "같은 동네":
            where = f"같은 동네({f['admin_area']})"
        elif f.get("distance_km") is not None:
            where = f"약 {f['distance_km']:.1f}km 떨어진 {f['admin_area']}"
        else:
            where = f.get("admin_area") or "가까운 곳"
        parts.append(f"{where}에서 같은 재료 축제({f['name']})가 열려요")
    return f"{month}월에는 " + ", ".join(parts) + "."


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
            out.append("같은 재료 축제: " + festivals_text(e["overlapping_festivals"]))
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
                tag = f" ({h['data_label']})" if h.get("is_synthetic") else ""
                stops = ", ".join(
                    f"{x['stop_name']} {x['daily_boarding']:,.1f}명" for x in h["stops"]
                )
                out.append(f"{label}({h['hours']}) 하루 승차: {stops}{tag}")
    elif r.check == "check_target":
        if a := e.get("age_share"):
            out.append(
                f"대상 연령({', '.join(e['age_groups'])}) {a['dong_share_pct']}% / 제주 평균 {a['jeju_share_pct']}% ({a['ratio']}배)"
                + (f" · {e['excluded_note']}" if e.get("excluded_note") else "")
            )
        if s := e.get("sex_share"):
            out.append(
                f"성별({e['sex']}) {s['dong_share_pct']}% / 제주 평균 {s['jeju_share_pct']}% ({s['ratio']}배)"
            )
        if f := e.get("flow"):
            out.append(
                f"참고 4-11 방문인구 대상 비중 {f['dong_share_pct']}% / 제주 {f['jeju_share_pct']}% ({f.get('data_label', '')})"
            )
    elif r.check == "check_risk":
        if e.get("same_material_festivals"):
            out.append("같은 재료 축제: " + festivals_text(e["same_material_festivals"]))
        if res := e.get("residential"):
            for a in res["areas"]:
                out.append(
                    f"{a['admin_area']} 야간 거주인구 제주 동네 평균의 {a['ratio']}배"
                    + (SYNTHETIC_TAG if res["is_synthetic"] else "")
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
                + (SYNTHETIC_TAG if c.get("is_synthetic") else "")
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


def check_card_summary(r: CheckResult) -> dict:
    """첫 화면의 대표 수치. 상세 원문·출처는 펼친 영역에 보존한다."""
    e = r.evidence or {}
    value, label = WAITING, "자료가 준비되면 확인할 수 있어요"
    synthetic = r.is_synthetic
    if r.check == "check_timing" and (indices := e.get("outsider_visitors_index")):
        value = " · ".join(f"{v:.2f}" for v in indices.values())
        label = months_text([int(m) for m in indices]) + " 관광 목적 사용량 지표 · 연평균 1"
    elif r.check == "check_venue" and (places := e.get("candidate_places")):
        first = places[0]
        distance = first.get("stop_distance_m")
        value = f"{distance:,.0f}m" if distance is not None else f"후보 {len(places)}곳"
        label = (
            f"{first.get('stop_name') or '정류소'}까지 · {first['name']} 후보 기준"
            if distance is not None else "장소 후보 상세 비교"
        )
    elif r.check == "check_target" and (share := e.get("age_share") or e.get("sex_share")):
        value = f"{share['dong_share_pct']:.1f}%"
        label = f"대상 이용 비중 · 제주 평균 {share['jeju_share_pct']:.1f}%"
    elif r.check == "check_risk" and (res := e.get("residential")) and res.get("areas"):
        area = max(res["areas"], key=lambda a: a["ratio"])
        value = f"{area['ratio']:g}배"
        label = f"{area['admin_area']} 야간 거주인구 · 제주 동네 평균 대비"
        synthetic = res.get("is_synthetic", False)
    elif r.check == "check_budget":
        value = won(e.get("input_krw"))
        label = "입력한 예산"
        if e.get("format_median_krw") is not None:
            label += f" · 유사 형식 중앙값 {won(e['format_median_krw'])}"
    preferred = {
        "check_timing": ("와이파이 관광 사용량", "날씨는"),
        "check_venue": ("셔틀", "귀가 버스", "가상 데이터"),
        "check_target": ("고령층", "사용자 수"),
        "check_risk": ("가상 데이터", "가짜 데이터"),
        "check_budget": ("방문객",),
    }
    warning = next(
        (w for phrase in preferred[r.check] for w in r.warnings if phrase in w),
        next(iter(r.warnings), ""),
    )
    if r.check == "check_timing" and "와이파이 관광 사용량" in warning:
        warning = "관광 목적 와이파이 사용량으로 대신 본 지표이며, 실제 관광객 수는 아니에요."
    elif r.check == "check_venue" and "셔틀" in warning:
        warning = "야간 귀가 버스편을 확인하고, 부족하면 셔틀 운영을 검토해주세요."
        if (e.get("night_return") or {}).get("is_synthetic"):
            warning += " 시간대 이용량은 가상 데이터예요."
    elif r.check == "check_target" and "고령층" in warning:
        warning = "와이파이 이용자 기준이라 실제 방문객의 연령 구성과 다를 수 있어요."
    elif r.check == "check_risk" and synthetic:
        warning = "위 수치는 가상 데이터 참고값이에요. 운영 전 실데이터로 확인해주세요."
    reason = r.reason.split("추천 주:")[0].strip()
    if r.check == "check_venue" and r.status == "pass" and (places := e.get("candidate_places")):
        reason = f"{places[0]['name']} 후보 근처에 걸어갈 수 있는 버스 정류소가 있어요."
    if r.check == "check_budget":
        reason = reason.split("같은 형식(")[0].strip()
    return {"reason": reason, "value": value, "label": label,
            "synthetic": synthetic, "warning": warning}


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
        if mc.get("near_festivals") and not mc.get("near_downgraded"):
            sentences.append(near_festival_sentence(m, mc["near_festivals"]))
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


def _change_note(source, next_results, change) -> str | None:
    """바뀐 점 ⚠️ 안내: 입력 계절 밖으로 바꿨으면 그 사실 + 바꾼 달이 조건부인 이유."""
    outside = None
    if source is not None and source.check == "check_timing":
        outside = (source.evidence or {}).get("season_outside_suggestion")
    notes = [n for n in (outside, _after_note(next_results, change)) if n]
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


def season_notice(run) -> str | None:
    """에이전트가 추천 월을 입력 계절 밖으로 바꿨으면 안내 문장 (check_timing evidence)."""
    notice = None
    for rd in run.rounds:
        for change in rd.changes:
            if change.field != "timing.recommended_months":
                continue
            r = _source_check(rd.results, change)
            if r is not None and r.check == "check_timing":
                notice = (r.evidence or {}).get("season_outside_suggestion") or None
    return notice


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
                    "note": _change_note(r, nxt, change),
                    "season": season,
                    "low_data": low_data_notes([r]) if r is not None else [],
                }
            )
    return out


# ---------- 입력·데모 카드 안내 ----------

DEMO_WARNING = (
    "AI를 쓸 수 없어 입력과 상관없는 예시 카드예요. 입력한 지역·계절·재료가 반영되지 않았어요."
)
# 사용자가 직접 예시 카드 보기를 켠 경우 (AI 오류로 예시 카드가 나온 경우는 DEMO_WARNING)
DEMO_TOGGLE_LABEL = "시연용 예시 카드 보기 (AI 없이)"
CHOSEN_DEMO_WARNING = (
    "예시 카드 보기가 켜져 있어요. 입력한 조건과 상관없는 시연용 카드예요. "
    "① 조건 입력에서 체크를 끄면 입력한 조건으로 AI가 카드를 만들어요."
)


def demo_warning_text(reason: str | None, diffs: list[str]) -> str:
    """예시 카드 위 노란 경고. 직접 켰으면 끄는 방법을, AI 오류면 이유를 알려준다."""
    other = ("\n\n입력과 다른 점: " + " / ".join(diffs)) if diffs else ""
    if reason == CHOSEN_DEMO_REASON:
        return f"### ⚠️ 시연용 예시 카드예요\n**{CHOSEN_DEMO_WARNING}**{other}"
    because = f"\n\n이유: {reason}" if reason else ""
    return f"### ⚠️ 예시 카드예요\n**{DEMO_WARNING}**{because}{other}"


def material_seasons() -> dict[str, list[int]]:
    """A의 소재 사전 가공본(research/reference/jeju_materials.csv)의 제철(months). 연중 재료는 빠진다."""
    import pandas as pd

    from research.materials import PUBLISHED_MATERIALS_PATH

    d = pd.read_csv(PUBLISHED_MATERIALS_PATH, dtype=str, keep_default_na=False)
    return {r.material: [int(m) for m in r.months.split("|")] for r in d.itertuples() if r.months}


def _material_in(text: str | None, seasons: dict) -> str | None:
    if not text:
        return None
    if text in seasons:
        return text
    return next((m for m in sorted(seasons, key=len, reverse=True) if m in text), None)


def season_conflict(request, seasons: dict | None = None) -> str | None:
    """입력 계절과 재료 제철이 겹치지 않으면 안내 문장 (막지는 않는다)."""
    from agent.idea_gen import SEASON_MONTHS

    if not request.season:
        return None
    seasons = material_seasons() if seasons is None else seasons
    material = _material_in(request.interest, seasons)
    if material is None or set(seasons[material]) & set(SEASON_MONTHS[request.season]):
        return None
    return (
        f"{josa(material, '은', '는')} {months_text(seasons[material])}이 제철이라 "
        f"{josa(request.season, '과', '와')} 맞지 않아요. 계절이나 재료를 바꿔보세요."
    )


def demo_differences(proposal, request) -> list[str]:
    """데모 카드가 입력과 다른 점: 지역·계절·재료."""
    from agent.idea_gen import SEASON_MONTHS

    diffs = []
    demo_region = proposal.input.region
    if (request.region or None) != demo_region:
        diffs.append(
            f"지역: 입력 {request.region or '제주 전역'} · 카드 {demo_region or '제주 전역'}"
        )
    months = sorted({m for c in proposal.ideas for m in c.timing.recommended_months})
    if request.season and not set(months) & set(SEASON_MONTHS[request.season]):
        diffs.append(f"계절: 입력 {request.season} · 카드 {months_text(months)}")
    materials = sorted({c.material for c in proposal.ideas})
    if request.interest and request.interest not in materials:
        diffs.append(f"재료: 입력 {request.interest} · 카드 {', '.join(materials)}")
    return diffs


# ---------- 확인 과정 요약, 직접 고친 안 ----------

ORDINALS = {1: "처음", 2: "두 번째", 3: "세 번째", 4: "네 번째"}
SCALE_LABELS = {"기본": "기본", "소규모 버전": "작게"}  # 화면 이름 (계약 값 → 화면)
NO_VENUE = "(정하지 않음)"


def _ro(word: str) -> str:
    """조사 (으)로: 받침이 없거나 ㄹ 받침이면 "로"."""
    ch = word.strip()[-1:]
    if not ch or not ("가" <= ch <= "힣"):
        return word + "로"
    jong = (ord(ch) - 0xAC00) % 28
    return word + ("로" if jong in (0, 8) else "으로")


def round_summary(run) -> list[str]:
    """확인 과정을 쉬운 말로. 고친 게 없으면 "5가지를 확인했어요."."""
    lines = []
    for rd in run.rounds:
        merged: list[dict] = []  # 같은 변경을 여러 확인이 제안하면 한 줄로
        for change in rd.changes:
            r = _source_check(rd.results, change)
            label = CHECK_LABELS.get(r.check, "확인") if r is not None else "확인"
            same = next(
                (m for m in merged
                 if (m["change"].field, m["change"].before, m["change"].after)
                 == (change.field, change.before, change.after)),
                None,
            )  # fmt: skip
            if same is None:
                merged.append({"change": change, "labels": [label]})
            elif label not in same["labels"]:
                same["labels"].append(label)
        for m in merged:
            c = m["change"]
            before, after = value_text(c.field, c.before), value_text(c.field, c.after)
            what = josa("·".join(m["labels"]), "이", "가")
            lines.append(
                f"{ORDINALS.get(rd.round, f'{rd.round}번째')} 확인에서 {what} 맞지 않아 "
                f"{before} → {_ro(after)} 바꾼 뒤 다시 확인했어요."
            )
    return lines or [f"{len(run.rounds[-1].results)}가지를 확인했어요."]


def edited_card(card, months: list[int], venue: dict | None, scale: str):
    """사용자가 직접 고른 개최 월·장소·규모로 바꾼 카드 (형식·재료는 그대로)."""
    from agent.draft_contracts import IdeaCard

    data = card.model_dump(mode="json")
    new_months = sorted(set(months))
    if new_months != data["timing"]["recommended_months"]:
        data["timing"]["recommended_months"] = new_months
        data["timing"]["jeju_festivals_in_month"] = None  # 달이 바뀌면 다시 세야 함
    data["venue"] = (
        [{"name": venue["name"], "admin_area": venue["admin_area"], "reason": "직접 고른 장소"}]
        if venue
        else []
    )
    data["budget"]["scale"] = scale
    return IdeaCard.model_validate(data)


def venue_choices(run) -> list[dict]:
    """직접 고르기용 장소 후보 (마지막 확인의 장소 후보 표)."""
    venue = next((r for r in run.rounds[-1].results if r.check == "check_venue"), None)
    if venue is None:
        return []
    return [
        {"name": c["name"], "admin_area": c["admin_area"]}
        for c in (venue.evidence or {}).get("candidate_places") or []
    ]


# ---------- 단계별 화면, 예시 카드 이유 ----------

STEPS = ["조건 입력", "아이디어", "데이터로 확인", "기획서", "홍보물"]
CIRCLED = "①②③④⑤"
NO_KEY_REASON = "AI 키가 설정되지 않았어요."
QUOTA_REASON = "오늘 AI 사용 한도를 넘었어요. 잠시 뒤 다시 해보세요."
CALL_FAIL_REASON = "AI 서버에 연결하지 못했어요."
# AI는 답했지만 카드 규칙 검사(후보 3개, 가설 숫자 등)를 통과하지 못함: 예시 카드 대신 다시 받기
CARDS_REJECTED_MESSAGE = "AI가 조건에 맞는 카드를 만들지 못했어요. 다시 시도해 주세요."
RETRY_CARDS_LABEL = "다시 받기"
CHOSEN_DEMO_REASON = "예시 카드 보기를 골랐어요."


def progress_text(step: int) -> str:
    """맨 위 진행 표시. 지금 단계만 굵게."""
    parts = []
    for i, name in enumerate(STEPS, start=1):
        label = f"{CIRCLED[i - 1]} {name}"
        parts.append(f"**{label}**" if i == step else label)
    return " → ".join(parts)


def selection_summary(request, card=None) -> str:
    """지금까지 고른 것 한 줄. 예: "서귀포시 대정읍 · 겨울 · 방어 · 예산 1,000만 원 / 고른 아이디어: …"."""
    parts = [
        request.region or "제주 전역",
        request.season or "계절 미정",
        request.interest or "소재 미정",
        f"예산 {won(request.budget_max_krw)}",
    ]
    text = " · ".join(parts)
    return text + (f" / 고른 아이디어: {card.title}" if card is not None else "")


def ai_failure_reason(exc) -> str | None:
    """예시 카드로 대신할 오류면 쉬운 이유 문장, 아니면 None.

    예시 카드는 AI를 쓸 수 없을 때만: 키 없음, 사용 한도(429), 연결·서버 오류(시간 초과, 5xx).
    키·모델 설정 오류(401·403·404 등)와 조건 문제는 None (원래 안내를 ① 조건 입력에 보여준다).
    카드 규칙 검사 실패는 None이고 cards_rejected로 따로 본다 (다시 받기).
    오류 원문(HTTP 코드 등)은 예시 카드 경고에 보여주지 않는다.
    """
    from agent.llm import LLMError

    msg = str(exc)
    cause = exc.__cause__
    if "AI 설정이 없어요" in msg:
        return NO_KEY_REASON
    if isinstance(cause, LLMError):
        text = str(cause)
        if "(HTTP 429)" in text:
            return QUOTA_REASON
        code = re.search(r"\(HTTP (\d{3})\)", text)
        if code is None or code.group(1).startswith("5"):
            return CALL_FAIL_REASON  # 연결 실패·시간 초과·서버 오류
    return None


RETRY_PLAN_LABEL = "다시 만들기"


def plan_failure_reason(exc) -> str:
    """기획서 생성 실패 이유를 쉬운 말 한 줄로 (오류 원문·HTTP 코드는 보여주지 않는다)."""
    from agent.llm import LLMError

    msg, cause = str(exc), exc.__cause__
    if "AI 설정이 없어요" in msg:
        return "AI 설정이 없어 기획서를 만들 수 없어요."
    if isinstance(cause, LLMError):
        if "(HTTP 429)" in str(cause):
            return "오늘 AI 사용 한도를 넘었어요. 잠시 뒤 다시 만들어 보세요."
        return "AI 서버에 연결하지 못했어요. 잠시 뒤 다시 만들어 보세요."
    if "규칙에 맞지 않아" in msg:
        if "정하지 않은 장소" in msg:
            return "AI가 정하지 않은 장소를 정한 것처럼 써서 기획서를 쓰지 않았어요. 다시 만들어 보세요."
        if "입력에 없는 숫자" in msg:
            return "AI가 근거에 없는 숫자를 써서 기획서를 쓰지 않았어요. 다시 만들어 보세요."
        return "AI가 쓴 기획서가 형식에 맞지 않았어요. 다시 만들어 보세요."
    return msg


def cards_rejected(exc) -> bool:
    """AI는 답했지만 카드 규칙 검사를 두 번 다 통과하지 못했는지 (agent.idea_cards)."""
    return "AI 응답이 형식에 맞지 않아" in str(exc)
