"""시기 확인 도구 check_timing의 실제 버전 (agent/fake_checks.py check_timing과 같은 입출력).

판정 기준 (설계 문서): 외지인이 연평균 이상 + 날씨가 평소보다 나쁘지 않은 주 + 같은 재료 축제와 안 겹침

추천 월마다 판정하고, 가장 나쁜 결과를 카드 결과로 쓴다.
- pending: 지역이 없거나 그 동네 외지인 지수(와이파이 자료)가 없음
- fail: 외지인 지수 < LOW_INDEX(0.8), 또는 그 달 모든 주가 나쁜 주
- conditional: 외지인 지수 0.8~1.0("평소보다 약간 적은 달"), 또는 같은 재료 제주 축제가 그 달에 있음
  (축제 날짜를 피할 주가 없어도 conditional + 경고)
- pass: 외지인 지수 1.0 이상 + 날씨 괜찮은 주 있음 + 같은 재료 축제 없음. 날씨 괜찮은 주를 추천 주로 표시

나쁜 주: 폭우 또는 바람이 같은 지점 평소의 BAD_RATIO배 이상이고, 9년 중 MIN_BAD_YEARS년 이상 발생.
비·더위는 여름에 늘 많아 판정에 쓰지 않고 참고 경고로만 붙인다.

fail 제안: 일부 달만 fail이면 그 달을 빼고, 전부 fail이면 통과하는 다른 달 중 외지인 지수가 가장 높은 달.
재료에 제철이 있으면 그 안에서만 고른다. 제철은 A의 소재 사전 가공본
(research/reference/jeju_materials.csv)의 months(제철·시기)와 months_basis(근거) 칸을 읽는다.

바꿔 끼우기: tools = {**FAKE_TOOLS, **REAL_TOOLS}

표 만들기: uv run python -m analytics.check_timing --build [--flow 4-11.csv]
  (먼저 uv run python -m analytics.weather 로 날씨 표를 만들어 둔다)
결과: data/processed/outsider_index.csv, data/processed/jeju_festival_dates.csv
"""

import argparse
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import pandas as pd

from agent.draft_contracts import CheckResult, IdeaCard, Suggestion, UserRequest
from analytics import outsider_index as oi
from analytics.weather import (
    FAR_STATION_KM,
    RELATIVE_LABELS,
    YEARS,
    timing_weather_evidence,
    week_label,
)

PROCESSED = Path("data/processed")
WEEKLY_PATH = PROCESSED / "weather_weekly_risk.csv"
MONTHLY_PATH = PROCESSED / "weather_monthly_risk.csv"
STATION_BY_DONG_PATH = PROCESSED / "weather_station_by_dong.csv"
FESTIVAL_DATES_PATH = PROCESSED / "jeju_festival_dates.csv"
FESTIVAL_PLAN_JEJU_PATH = PROCESSED / "festival_plan_2026_jeju.csv"

BAD_RATIO = 1.5
# 같은 재료·같은 달 축제가 같은 행정동이거나 동네 중심 거리 이 안이면 fail (그보다 멀면 conditional)
NEAR_FESTIVAL_KM = 10
SAME_AREA, NEAR_AREA, FAR_AREA = "같은 동네", "가까운 동네", "먼 동네"
UNKNOWN_AREA, UNKNOWN_DISTANCE = "장소 미확인", "거리 미확인"
MIN_BAD_YEARS = 2
JUDGED_RISKS = ("heavy_rain", "strong_wind")
REFERENCE_RISKS = ("rainy", "heat")
LAST_WEEK = 52  # 53주는 12월 31일 하루라 판정에서 뺀다
FESTIVAL_SOURCE = "문체부 2026년 지역축제 개최 계획(제주), 전국문화축제표준데이터 2026"
WIFI_WARNING = (
    "외지인 방문은 와이파이 관광 사용량으로 대신 본 값이에요. 사람 수가 아니라 데이터 사용량이고, "
    "4-11 유동인구 실데이터가 1년치 쌓이면 그것으로 바꿔요."
)
STATUS_ORDER = {"pass": 0, "conditional": 1, "fail": 2}
LOW_DATA_NOTICE = "이 지역은 자료가 적어 결과가 불안정할 수 있어요"
MIN_WIFI_PLACES = 5  # 외지인 지수에 쓴 장소가 이보다 적으면 (추자면 4곳)
ADMIN_BUILD_NOTE = "관리자용: uv run python -m analytics.real_checks --build 로 표를 만들어요."
# 외지인 지수 세 단계: PASS_INDEX 이상 pass, LOW_INDEX~PASS_INDEX conditional, LOW_INDEX 미만 fail
PASS_INDEX = 1.0
LOW_INDEX = 0.8


# ---------- 날씨: 나쁜 주 ----------


def week_days(week: int) -> tuple[int, int]:
    """주의 평년 기준 연중 날짜 범위 (시작, 끝)."""
    start = (week - 1) * 7 + 1
    return start, min(start + 6, 365)


def week_month(week: int) -> int:
    """주 시작일이 들어 있는 달."""
    return (date(2001, 1, 1) + timedelta(days=week_days(week)[0] - 1)).month


def week_text(week: int) -> str:
    """예: "8월 2주차 (8/13~8/19)"."""
    start, end = (date(2001, 1, 1) + timedelta(days=d - 1) for d in week_days(week))
    return f"{week_label(week)} ({start.month}/{start.day}~{end.month}/{end.day})"


def mark_bad_weeks(
    weekly: pd.DataFrame, ratio: float = BAD_RATIO, min_years: int = MIN_BAD_YEARS
) -> pd.DataFrame:
    """주마다 bad(나쁜 주)와 bad_reasons(예: "폭우 1.8배, 9년 중 3년")를 붙인다."""
    w = weekly[weekly["week"] <= LAST_WEEK].copy()
    w["month"] = w["week"].map(week_month)
    reasons = pd.Series([[] for _ in range(len(w))], index=w.index)
    for risk in JUDGED_RISKS:
        hit = (w[f"{risk}_ratio"] >= ratio) & (w[f"{risk}_years"] >= min_years)
        for i in w.index[hit.fillna(False)]:
            reasons[i].append(
                f"{RELATIVE_LABELS[risk]} {w.at[i, f'{risk}_ratio']:.1f}배, "
                f"{YEARS}년 중 {int(w.at[i, f'{risk}_years'])}년"
            )
    w["bad_reasons"] = reasons
    w["bad"] = reasons.map(bool)
    return w


def weather_fail_table(weekly: pd.DataFrame, ratio: float, min_years: int = MIN_BAD_YEARS):
    """지점 × 월: 그 달 모든 주가 나쁜 주인지 (날씨만으로 fail)."""
    w = mark_bad_weeks(weekly, ratio, min_years)
    return w.groupby(["station", "month"])["bad"].all().rename("all_bad").reset_index()


# ---------- 같은 재료 축제 ----------


def _day_of_year(d) -> int | None:
    if pd.isna(d):
        return None
    d = pd.Timestamp(d)
    return date(2001, d.month, min(d.day, 28) if d.month == 2 else d.day).timetuple().tm_yday


def festival_dates(plan: pd.DataFrame | None, standard: pd.DataFrame | None) -> pd.DataFrame:
    """제주 축제 날짜표: name, start, end, months, source, dates_known, admin_area.

    admin_area(행정동·읍면)는 계획의 admin_area 칸, 표준데이터는 미리 붙인 admin_area 칸(좌표 판정)을 쓴다.

    같은 축제(정규명)는 날짜가 있는 쪽, 그다음 문체부 2026 계획을 남긴다.
    날짜가 미정이면 시작 월만 있는 행으로 남긴다 (dates_known=False).
    """
    from research.trends import norm_name

    frames = []
    if plan is not None and len(plan):
        p = pd.DataFrame(
            {
                "name": plan["name"],
                "start": plan["start_date"],
                "end": plan["end_date"],
                "start_month": pd.to_numeric(plan["start_month"], errors="coerce"),
                "source": "문체부 2026 계획",
                "admin_area": plan.get("admin_area"),
                "priority": 0,
            }
        )
        frames.append(p)
    if standard is not None and len(standard):
        s = standard[~standard.get("is_duplicate", False)]
        frames.append(
            pd.DataFrame(
                {
                    "name": s["축제명"],
                    "start": s["축제시작일자"],
                    "end": s["축제종료일자"],
                    "start_month": pd.to_datetime(s["축제시작일자"], errors="coerce").dt.month,
                    "source": "전국문화축제표준데이터",
                    "admin_area": s.get("admin_area"),
                    "priority": 1,
                }
            )
        )
    if not frames:
        return pd.DataFrame(
            columns=["name", "start", "end", "months", "source", "dates_known", "admin_area"]
        )
    # 날짜는 합친 뒤에 바꾼다 (날짜가 모두 빈 표를 날짜형으로 합치면 pandas 경고가 난다)
    df = pd.concat([f.astype({"start": object, "end": object}) for f in frames], ignore_index=True)
    df["start"] = pd.to_datetime(df["start"], errors="coerce")
    df["end"] = pd.to_datetime(df["end"], errors="coerce")
    df["name"] = df["name"].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    df["end"] = df["end"].fillna(df["start"])
    df["dates_known"] = df["start"].notna()
    df["_k"] = df["name"].map(norm_name)
    # 남기는 행에 동네가 없으면 같은 축제의 다른 출처 행에서 가져온다
    df["admin_area"] = df.groupby("_k")["admin_area"].transform(
        lambda a: a.dropna().iloc[0] if a.notna().any() else None
    )
    df = df.sort_values(["dates_known", "priority"], ascending=[False, True])
    df = df.drop_duplicates("_k").drop(columns=["_k", "priority"])

    def months(r) -> str:
        if r.dates_known:
            ms = pd.date_range(r.start.replace(day=1), r.end, freq="MS").month
            return "|".join(str(m) for m in sorted(set(ms)))
        return "" if pd.isna(r.start_month) else str(int(r.start_month))

    df["months"] = [months(r) for r in df.itertuples()]
    df = df[df["months"] != ""]
    cols = ["name", "start", "end", "months", "source", "dates_known", "admin_area"]
    return df[cols].reset_index(drop=True)


def _festival_overlaps_week(fest, week: int) -> bool:
    """날짜가 확인된 축제가 그 주와 겹치는지. 날짜 미확인 축제는 따로 경고한다."""
    if not fest["dates_known"]:
        return False
    s, e = _day_of_year(fest["start"]), _day_of_year(fest["end"])
    ws, we = week_days(week)
    if e < s:  # 해를 넘기는 축제 (12월 ~ 1월)
        return ws <= e or we >= s
    return ws <= e and we >= s


def material_pattern(material: str, keywords: pd.DataFrame | None) -> tuple[str, bool]:
    """재료의 축제명 검색어 (소재 사전 키워드). 사전에 없으면 재료 이름 그대로."""
    if keywords is not None:
        row = keywords[keywords["material"] == material]
        if len(row):
            return row["keywords"].iloc[0], True
    return re.escape(material), False


# ---------- 판정 ----------


@dataclass
class TimingData:
    weekly: pd.DataFrame | None  # mark_bad_weeks를 거친 표
    monthly: pd.DataFrame | None
    station_by_dong: pd.DataFrame | None
    outsider: pd.DataFrame | None
    festivals: pd.DataFrame = field(default_factory=pd.DataFrame)
    keywords: pd.DataFrame | None = None
    # 재료 → (제철 월, 근거). 소재 사전에서 제철이 비어 있으면(연중) 넣지 않는다
    material_season: dict[str, tuple[list[int], str]] = field(default_factory=dict)


def _read(path: Path, **kw) -> pd.DataFrame | None:
    """analytics/reference/에 같은 이름의 표가 있으면 그것을 먼저 읽는다."""
    from analytics.reference_data import reference_first

    path = reference_first(path.name, path)
    return pd.read_csv(path, encoding="utf-8-sig", **kw) if path.exists() else None


@lru_cache(maxsize=1)
def load_timing_data() -> TimingData:
    """미리 만든 표를 읽는다. 없는 표는 None (해당 판정은 pending)."""
    from research.materials import PUBLISHED_MATERIALS_PATH, load_keywords

    weekly = _read(WEEKLY_PATH)
    festivals = _read(FESTIVAL_DATES_PATH, parse_dates=["start", "end"], dtype={"months": str})
    mat = pd.read_csv(PUBLISHED_MATERIALS_PATH, dtype=str, keep_default_na=False)
    return TimingData(
        weekly=None if weekly is None else mark_bad_weeks(weekly),
        monthly=_read(MONTHLY_PATH),
        station_by_dong=_read(STATION_BY_DONG_PATH),
        outsider=_read(oi.OUTPUT_PATH),
        festivals=pd.DataFrame() if festivals is None else festivals,
        keywords=load_keywords(),
        material_season={
            r.material: ([int(m) for m in r.months.split("|")], r.months_basis)
            for r in mat.itertuples()
            if r.months
        },
    )


@dataclass
class MonthCheck:
    month: int
    status: str
    index: float | None
    good_weeks: list[int]
    bad_weeks: list[tuple[int, list[str]]]
    festivals: list[dict]
    recommended_weeks: list[int]
    unavoidable: bool  # 날짜가 확인된 같은 재료 축제를 피할 날씨 괜찮은 주가 없음
    near_festivals: list[dict] = field(default_factory=list)  # 같은 동네·10km 이내 같은 재료 축제
    near_downgraded: bool = False  # 가까운 축제만 이유인데 고를 다른 달이 없어 conditional로 둠

    @property
    def only_near(self) -> bool:
        """fail 이유가 가까운 같은 재료 축제뿐인지 (외지인·날씨는 통과)."""
        return bool(self.near_festivals) and self.index >= LOW_INDEX and bool(self.good_weeks)

    @property
    def slightly_low(self) -> bool:
        return LOW_INDEX <= self.index < PASS_INDEX

    def fail_reason(self) -> str | None:
        low = self.index < LOW_INDEX
        low_text = f"외지인 방문 지수({self.index:.2f})가 {LOW_INDEX}보다 낮"
        weather = "모든 주가 평소보다 폭우·바람이 잦아요"
        if low and not self.good_weeks:
            text = f"{self.month}월은 {low_text}고, {weather}"
        elif low:
            text = f"{self.month}월은 {low_text}아요"
        elif not self.good_weeks:
            text = f"{self.month}월은 {weather}"
        else:
            text = None
        if self.near_festivals and not self.near_downgraded:
            near = ", ".join(
                f"{f['name']}({f['admin_area']}, {festival_place_text(f)})"
                for f in self.near_festivals
            )
            near_text = f"가까운 곳에서 같은 재료 축제가 열려요: {near}"
            text = (
                f"{text}. {self.month}월에는 {near_text}"
                if text
                else f"{self.month}월에는 {near_text}"
            )
        return text


def festival_place_text(f: dict) -> str:
    """ "같은 동네", "약 7km", "장소 미확인" 같은 짧은 표시."""
    if f["relation"] == SAME_AREA:
        return SAME_AREA
    if f["distance_km"] is not None:
        return f"약 {f['distance_km']:.0f}km"
    return f["relation"]


def _centroids(station_by_dong) -> dict[str, tuple[float, float]]:
    """행정동 → 경계 중심 좌표 (weather_station_by_dong.csv의 centroid_lat·centroid_lon)."""
    if station_by_dong is None or not {"centroid_lat", "centroid_lon"} <= set(station_by_dong):
        return {}
    return {
        r.admin_area: (float(r.centroid_lat), float(r.centroid_lon))
        for r in station_by_dong.itertuples()
    }


def festival_relation(area, region: str | None, centroids: dict) -> tuple[str, float | None]:
    """축제 행정동과 입력 지역의 관계와 동네 중심 거리(km)."""
    from analytics.weather import _km

    if not isinstance(area, str) or not area:
        return UNKNOWN_AREA, None
    if area == region:
        return SAME_AREA, 0.0
    if area not in centroids or region not in centroids:
        return UNKNOWN_DISTANCE, None
    km = round(_km(*centroids[area], *centroids[region]), 1)
    return (NEAR_AREA if km <= NEAR_FESTIVAL_KM else FAR_AREA), km


def _month_check(month, index, station_weeks, fests, region=None, centroids=None) -> MonthCheck:
    weeks = station_weeks[station_weeks["month"] == month]
    good = weeks.loc[~weeks["bad"], "week"].astype(int).tolist()
    bad = [(int(r.week), r.bad_reasons) for r in weeks[weeks["bad"]].itertuples()]
    in_month = [f for _, f in fests.iterrows() if str(month) in f["months"].split("|")]
    free = [w for w in good if not any(_festival_overlaps_week(f, w) for f in in_month)]
    unavoidable = bool(in_month and good and not free)
    festivals = []
    for f in in_month:
        area = f.get("admin_area") if hasattr(f, "get") else None
        relation, km = festival_relation(area, region, centroids or {})
        festivals.append(
            {
                "name": f["name"],
                "months": [int(m) for m in str(f["months"]).split("|") if m],
                "start": f["start"].date().isoformat() if f["dates_known"] else None,
                "end": f["end"].date().isoformat() if f["dates_known"] else None,
                "dates_known": bool(f["dates_known"]),
                "admin_area": area if isinstance(area, str) and area else None,
                "distance_km": km,
                "relation": relation,
                "source": f["source"],
            }
        )
    near = [f for f in festivals if f["relation"] in (SAME_AREA, NEAR_AREA)]
    if index < LOW_INDEX or not good or near:
        status = "fail"
    elif index < PASS_INDEX or in_month:
        status = "conditional"
    else:
        status = "pass"
    return MonthCheck(
        month=month,
        status=status,
        index=index,
        good_weeks=good,
        bad_weeks=bad,
        festivals=festivals,
        recommended_weeks=free or good,
        unavoidable=unavoidable,
        near_festivals=near,
    )


def _pending(reason: str, evidence: dict, sources: list[str], warnings: list[str]) -> CheckResult:
    return CheckResult(
        check="check_timing",
        status="pending",
        reason=reason,
        evidence=evidence,
        sources=sources,
        warnings=[reason, *warnings],
    )


def _suggest(card, checks, all_checks, data) -> Suggestion | None:
    months = card.timing.recommended_months
    failed = [c for c in checks if c.status == "fail"]
    if len(failed) < len(checks):
        keep = [m for m in months if m not in {c.month for c in failed}]
        why = "; ".join(c.fail_reason() for c in failed) + ". 그 달을 빼요."
        return Suggestion(field="timing.recommended_months", value=keep, why=why)
    season, _basis = data.material_season.get(card.material, (None, None))
    for wanted in ("pass", "conditional"):
        options = [
            c
            for c in all_checks
            if c.status == wanted and c.month not in months and (not season or c.month in season)
        ]
        if options:
            best = max(options, key=lambda c: c.index)
            why = (
                f"추천 월이 모두 확인을 통과하지 못해, 다른 달 중 "
                f"{'통과하고' if wanted == 'pass' else '조건부로 통과하고'} "
                f"외지인 방문 지수가 가장 높은 "
                f"{best.month}월({best.index:.2f})로 바꿔요."
            )
            if season:
                # 제철 근거(내부 문서)는 evidence["material_season"]에만 남긴다
                why += f" 재료 제철({'·'.join(map(str, season))}월) 안에서 골랐어요."
            return Suggestion(field="timing.recommended_months", value=[best.month], why=why)
    return None


def check_timing(
    card: IdeaCard, request: UserRequest, data: TimingData | None = None
) -> CheckResult:
    data = data or load_timing_data()
    months = sorted(set(card.timing.recommended_months))
    region = request.region
    evidence: dict = {"months": months, "low_months": [], "outsider_visitors_index": None}
    sources: list[str] = []
    warnings: list[str] = []

    if not region:
        return _pending("지역이 없어 외지인 방문과 날씨를 확인하지 못했어요.", evidence, [], [])
    if data.outsider is None or data.weekly is None or data.station_by_dong is None:
        return _pending(
            "시기 확인용 표가 아직 없어요. 관리자에게 표 만들기를 요청해 주세요.",
            evidence,
            [],
            [ADMIN_BUILD_NOTE],
        )

    weather, w_sources, w_warnings = timing_weather_evidence(
        region, months, data.monthly, data.station_by_dong
    )
    evidence.update(weather)
    sources += w_sources
    warnings += w_warnings
    rows = data.outsider[data.outsider["admin_area"] == region]
    if rows.empty or weather["weather_station"] is None:
        return _pending(
            f"{region}에는 와이파이 관광 사용량 자료가 없어 외지인 방문을 확인하지 못했어요.",
            evidence,
            sources,
            warnings,
        )
    index = rows.set_index("month")["index"]
    source = rows["source"].iloc[0]
    is_synthetic = bool(rows["is_synthetic"].any())
    sources.append(source)
    if source.startswith(oi.WIFI_SOURCE):
        warnings.append(WIFI_WARNING)
    if note := oi.place_count_warning(rows):
        warnings.append(note)
    low_data = []
    places = pd.to_numeric(rows["places"], errors="coerce").min()
    if source.startswith(oi.WIFI_SOURCE) and pd.notna(places) and places < MIN_WIFI_PLACES:
        low_data.append(f"관광객 지표에 쓴 와이파이 장소가 {places:.0f}곳뿐이에요")
    distance = weather.get("station_distance_km")
    if distance is not None and distance > FAR_STATION_KM:
        low_data.append(f"날씨 지점({weather['weather_station']})이 {distance:.0f}km 떨어져 있어요")
    evidence["low_data"] = low_data
    if low_data:
        # 날씨 지점 거리 경고는 자료 부족 안내 한 문장으로 합친다
        warnings = [w for w in warnings if not w.startswith("날씨 지점(")]
        warnings.append(f"{LOW_DATA_NOTICE}: {', '.join(low_data)}.")
    evidence["outsider_visitors_index"] = {m: round(float(index[m]), 2) for m in months}
    evidence["outsider_index_source"] = source
    season = data.material_season.get(card.material)
    evidence["material_season"] = (
        {"months": season[0], "basis": season[1]} if season else None
    )  # basis는 팀 내부 근거라 화면에 보여주지 않는다
    evidence["low_months"] = [m for m in months if index[m] < LOW_INDEX]
    evidence["slightly_low_months"] = [m for m in months if LOW_INDEX <= index[m] < PASS_INDEX]
    evidence["outsider_index_rule"] = (
        f"{PASS_INDEX} 이상 pass, {LOW_INDEX}~{PASS_INDEX} conditional, {LOW_INDEX} 미만 fail"
    )

    # 같은 재료 축제
    pattern, known = material_pattern(card.material, data.keywords)
    if not known:
        warnings.append(
            f"'{card.material}'은(는) 소재 사전에 없어 재료 이름 그대로 축제명을 찾았어요."
        )
    fests = data.festivals
    if len(fests):
        fests = fests[fests["name"].str.contains(pattern, regex=True)]
        sources.append(FESTIVAL_SOURCE)

    station_weeks = data.weekly[data.weekly["station"] == weather["weather_station"]]
    centroids = _centroids(data.station_by_dong)
    all_checks = [
        _month_check(m, float(index[m]), station_weeks, fests, region, centroids)
        for m in range(1, 13)
    ]
    checks = [c for c in all_checks if c.month in months]
    status = max((c.status for c in checks), key=STATUS_ORDER.get)
    suggestion = _suggest(card, checks, all_checks, data) if status == "fail" else None
    if status == "fail" and suggestion is None:
        # 가까운 같은 재료 축제만 이유인데 피할 다른 달이 없으면 conditional + 경고 (외지인·날씨 fail은 그대로)
        for c in checks:
            if c.status == "fail" and c.only_near:
                c.status, c.near_downgraded = "conditional", True
                names = ", ".join(f"{f['name']}({f['admin_area']})" for f in c.near_festivals)
                warnings.append(
                    f"{c.month}월에는 가까운 곳에서 같은 재료 축제({names})가 열리지만, "
                    "제철 안에서 외지인·날씨 기준을 통과하는 다른 달이 없어요. "
                    "날짜를 겹치지 않게 잡고 차별점을 분명히 해 주세요."
                )
        status = max((c.status for c in checks), key=STATUS_ORDER.get)

    evidence.update(
        {
            "weather_rule": (
                f"폭우·바람이 같은 지점 평소의 {BAD_RATIO}배 이상이고 "
                f"{YEARS}년 중 {MIN_BAD_YEARS}년 이상 있었던 주를 나쁜 주로 봄"
            ),
            "bad_weather_months": [c.month for c in checks if not c.good_weeks],
            "recommended_weeks": [week_text(w) for c in checks for w in c.recommended_weeks],
            "recommended_week_numbers": [w for c in checks for w in c.recommended_weeks],
            "near_festival_rule": (
                f"같은 재료·같은 달 축제가 같은 행정동이거나 동네 중심 거리 {NEAR_FESTIVAL_KM}km 이내면 "
                "그 달은 fail, 더 멀면 conditional"
            ),
            "overlapping_festivals": [f | {"month": c.month} for c in checks for f in c.festivals],
            "month_checks": [
                {
                    "month": c.month,
                    "status": c.status,
                    "outsider_visitors_index": round(c.index, 2),
                    "good_weeks": [week_text(w) for w in c.good_weeks],
                    "bad_weeks": [{"week": week_text(w), "why": r} for w, r in c.bad_weeks],
                    "overlapping_festivals": [f["name"] for f in c.festivals],
                }
                for c in checks
            ],
        }
    )
    for c in checks:
        if c.slightly_low:
            warnings.append(
                f"{c.month}월은 외지인 방문이 평소보다 약간 적은 달이에요 (지수 {c.index:.2f})."
            )
        if c.unavoidable:
            names = ", ".join(f["name"] for f in c.festivals if f["dates_known"])
            warnings.append(
                f"{c.month}월에는 날씨 괜찮은 주가 모두 같은 재료 축제({names}) 기간과 겹쳐요. "
                "날짜를 피할 수 없으니 차별점을 분명히 하거나 다른 달을 검토해 주세요."
            )
        unknown = [f["name"] for f in c.festivals if not f["dates_known"]]
        if unknown:
            warnings.append(
                f"{c.month}월 같은 재료 축제 중 날짜 미확인: {', '.join(unknown)}. "
                "추천 주와 겹치는지 직접 확인해 주세요."
            )
        by_month = next((m for m in weather["weather_by_month"] if m["month"] == c.month), None)
        if by_month:
            more = [
                RELATIVE_LABELS[k] for k in REFERENCE_RISKS if (by_month[f"{k}_ratio"] or 0) > 1
            ]
            if more:
                warnings.append(
                    f"참고: {c.month}월은 평소보다 {'·'.join(more)}가 많아요 (판정에는 쓰지 않음)."
                )

    if status == "fail":
        reason = "; ".join(c.fail_reason() for c in checks if c.status == "fail") + "."
        if suggestion is None:
            warnings.append("통과하는 다른 달이 없어 추천 월을 고치는 제안을 하지 못했어요.")
    else:
        suggestion = None
        weeks = ", ".join(evidence["recommended_weeks"])
        if status == "conditional":
            parts = []
            low = [c for c in checks if c.slightly_low]
            if low:
                parts.append(
                    ", ".join(f"{c.month}월" for c in low)
                    + "은 외지인 방문이 평소보다 약간 적은 달이에요."
                )
            names = ", ".join(dict.fromkeys(f["name"] for f in evidence["overlapping_festivals"]))
            if names:
                parts.append(f"같은 재료 제주 축제({names})가 같은 달에 있어요.")
            parts.append(f"추천 주: {weeks}.")
            reason = " ".join(parts)
        else:
            reason = (
                "추천 월의 외지인 방문이 연평균 이상이고, 같은 재료 제주 축제와 겹치지 않아요. "
                f"날씨 괜찮은 주: {weeks}."
            )
    return CheckResult(
        check="check_timing",
        status=status,
        reason=reason,
        evidence=evidence,
        sources=list(dict.fromkeys(sources)),
        suggestion=suggestion,
        is_synthetic=is_synthetic,
        warnings=list(dict.fromkeys(warnings)),
    )


REAL_TOOLS = {"check_timing": check_timing}


# ---------- 표 만들기 ----------


def build(flow_path: Path | None = None) -> None:
    from analytics.loaders import load_festivals
    from analytics.report_area_link import table

    PROCESSED.mkdir(parents=True, exist_ok=True)
    from analytics.reference_data import load_wifi_usage_agg

    usage = load_wifi_usage_agg()
    usage = usage[usage["visit_type"].notna()]
    wifi = oi.wifi_outsider_index(usage, oi.wifi_place_areas(usage["wifi_place_name"]))
    flow = None
    if flow_path is not None:
        from analytics.validate_flow import validate_flow

        report = validate_flow(flow_path)
        if report.data is None:
            raise SystemExit(report.summary())
        # data/demo/ 아래 파일은 합성 데이터
        flow = oi.flow_outsider_index(report.data, is_synthetic="demo" in Path(flow_path).parts)
        if flow is None:
            print(f"4-11 자료가 {oi.MIN_FLOW_MONTHS}개월 미만이라 와이파이 지수를 써요.")
    index = oi.choose_index(flow, wifi)
    index.to_csv(oi.OUTPUT_PATH, index=False, encoding="utf-8-sig")

    plan = _read(FESTIVAL_PLAN_JEJU_PATH)
    standard = load_festivals()
    from analytics.boundary import load_jeju_boundaries

    boundaries = load_jeju_boundaries()
    standard["admin_area"] = [
        boundaries.locate(lat, lon)
        for lat, lon in zip(standard["위도"], standard["경도"], strict=True)
    ]
    fests = festival_dates(plan, standard)
    fests.to_csv(FESTIVAL_DATES_PATH, index=False, encoding="utf-8-sig")

    print(f"## 외지인 지수: {index['admin_area'].nunique()}개 동네 ({index['source'].iloc[0]})")
    wide = index.pivot(index="admin_area", columns="month", values="index").round(2)
    print(table(wide.reset_index()))
    print(f"\n## 제주 축제 날짜표: {len(fests)}건 (날짜 미확인 {(~fests['dates_known']).sum()}건)")

    weekly = pd.read_csv(WEEKLY_PATH, encoding="utf-8-sig")
    print(f"\n## 날씨만으로 fail (지점 × 월 48개 중, {YEARS}년 중 {MIN_BAD_YEARS}년 이상)")
    for ratio in (1.5, 2.0):
        t = weather_fail_table(weekly, ratio)
        bad = t[t["all_bad"]]
        listing = ", ".join(f"{r.station} {r.month}월" for r in bad.itertuples()) or "없음"
        print(f"- {ratio}배: {len(bad)}개 ({listing})")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="check_timing용 표 만들기")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--flow", type=Path, help="4-11 유동인구 CSV (12개월 이상이면 우선 사용)")
    args = parser.parse_args(argv)
    if args.build:
        build(args.flow)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
