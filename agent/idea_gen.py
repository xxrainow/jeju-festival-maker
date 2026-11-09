"""아이디어 후보 조합과 점수 (설계 기획서 5절, 9-1절). 숫자는 모두 여기서 코드로 계산한다.

후보 = 전국 상승 형식 8개 × 제주 재료. 궁합표로 어색한 조합을 거르고, 계절로 안 되는 조합을 빼고,
점수 상위 후보를 LLM에 넘긴다 (LLM은 3개를 고르고 문장만 쓴다).

점수 (질문 3개, 같은 비중. 가중치는 기획서 8절 "가중치 재조정" 전 임시값):
1. 요즘 뜨는 형식인가? = 신설리프트와 신설 수를 8개 형식 중 최댓값으로 나눈 평균
2. 제주에 없는 형식인가? = 1 / (1 + 같은 형식 제주 축제 수)
3. 관광객이 좋아하는 제주 재료인가? = 제주 소재 사전(research/materials.py)의 소재 강점
   (관련 장소 관광 사용량 비중 + 전국 희소성). 사전이 없으면 임시 목록(SEED_MATERIALS)과
   제주 소재 강점비(제주 비중 ÷ 전국 비중)를 쓴다
- 궁합 △는 점수 절반, ✕는 후보에서 제외
- 입력 목적에 맞는 형식은 +PURPOSE_BONUS
"""

import json
from dataclasses import dataclass, field

import pandas as pd
from pydantic import BaseModel

from agent.draft_contracts import (
    AppliedRules,
    BudgetExample,
    DesignatedFestival,
    ExistingFestival,
    FestivalFormat,
    IdeaBudget,
    IdeaCard,
    IdeaEvidence,
    IdeaReference,
    IdeaTiming,
    JejuGapEvidence,
    MaterialCategory,
    TrendEvidence,
    UserRequest,
    VisitorInterestEvidence,
)

FORMATS: tuple[str, ...] = (
    "여름·물놀이", "시장·상권", "정원·가드닝", "푸드·디저트",
    "맥주·주류", "도심·거리·골목", "야간·빛·드론", "영화·책·아트",
)  # fmt: skip
CATEGORIES: tuple[str, ...] = ("자연", "농산물", "수산물", "문화·생활", "경관")

# 포맷-소재 궁합표 (기획서 5절 초안, 팀이 직접 고친다). 열 순서는 CATEGORIES
_PAIRING_ROWS = {
    "여름·물놀이":   "○✕△△△",
    "시장·상권":     "✕○○○✕",
    "정원·가드닝":   "○○✕△○",
    "푸드·디저트":   "✕○○△✕",
    "맥주·주류":     "△○○△△",
    "도심·거리·골목": "✕△△○△",
    "야간·빛·드론":  "○△○○○",
    "영화·책·아트":  "△✕✕○○",
}  # fmt: skip
PAIRING: dict[str, dict[str, str]] = {
    fmt: dict(zip(CATEGORIES, row, strict=True)) for fmt, row in _PAIRING_ROWS.items()
}

SEASON_MONTHS = {"봄": (3, 4, 5), "여름": (6, 7, 8), "가을": (9, 10, 11), "겨울": (12, 1, 2)}
FORMAT_MONTHS: dict[str, tuple[int, ...]] = {"여름·물놀이": (6, 7, 8)}  # 계절이 정해진 형식

# 목적 → 가산점 형식. 기획서 9-1에 예시가 있는 목적만 넣었다. 나머지 목적은 팀이 정한다
PURPOSE_BOOST: dict[str, tuple[str, ...]] = {
    "지역 상권 활성화": ("시장·상권", "푸드·디저트", "도심·거리·골목"),
}
PURPOSE_BONUS = 0.1
TRIANGLE_FACTOR = 0.5
NEUTRAL_INTEREST = 0.5
TOP_N = 10  # LLM에 넘기는 후보 수
MAX_EXISTING = 3  # 후보·카드에 붙이는 기존 제주 축제 수
MAX_REPEAT = 3  # 상위 후보 안에서 같은 형식·같은 재료의 최대 개수
IDEA_COUNT = 3
INTEREST_NOTICE = (
    "제주 소재 사전이 없어 임시 재료 목록을 썼어요. 관광객 관심 지표 대신 제주 축제의 소재 비중을 "
    "순위에 임시로 썼어요."
)
PENDING_INTEREST_NOTICE = (
    "와이파이 장소와 연결되지 않은 재료(주로 수산물·농산물)는 관광객 관심 지표가 없어 중간값으로 "
    "계산했어요."
)
DICTIONARY_SOURCE = "제주 소재 사전 (와이파이 장소별 방문자별 사용량 2023-01~2024-12)"


@dataclass(frozen=True)
class Material:
    name: str
    category: str  # CATEGORIES 중 하나
    months: tuple[int, ...] | None = None  # 소재가 성립하는 월. None = 연중
    strength_tag: str | None = None  # (임시 목록용) 강점비를 가져올 트렌드 태그
    strength: float | None = None  # (사전) 소재 강점 0~1. 있으면 strength_tag보다 우선
    tourist_share_pct: float | None = None  # (사전) 관련 장소 관광 사용량 비중. 없으면 pending
    existing_festivals: tuple[
        tuple[str, int | None], ...
    ] = ()  # 같은 재료의 기존 제주 축제 (이름, 월)


# 제주 소재 사전(기획서 6절, D 단계)이 나오기 전 임시 목록. 제철 월은 팀 검수 전 가정이다
SEED_MATERIALS: tuple[Material, ...] = (
    Material("감귤", "농산물", (10, 11, 12, 1), "농축산 특산"),
    Material("흑돼지", "농산물", None, "농축산 특산"),
    Material("방어", "수산물", (11, 12, 1, 2), "수산물"),
    Material("갈치", "수산물", None, "수산물"),
    Material("유채꽃", "자연", (3, 4), "봄꽃"),
    Material("용천수", "자연", (7, 8), None),
    Material("해녀", "문화·생활", None, None),
    Material("돌담길", "경관", None, None),
)


@dataclass(frozen=True)
class FormatStats:
    new_count: int
    new_lift: float
    verdict: str
    jeju_count: int
    budgets_krw: tuple[tuple[str, int], ...] = ()  # (축제명, 예산 원), 오름차순
    designated: tuple[tuple[str, str], ...] = ()  # (지정명, 2026 등급)
    supply_signal: str = "↑"  # 공급 신호 (↑ / → / ↓)

    @property
    def interpretation(self) -> tuple[str, str]:
        """(해석, 전략). 기획서 4절 공급 신호 × 지정 사례."""
        from research.designation import interpret

        return interpret(self.supply_signal, len(self.designated))


@dataclass(frozen=True)
class TrendData:
    """후보 점수와 카드 근거에 쓰는 숫자 묶음. 실데이터는 from_panel, 테스트는 직접 만든다."""

    formats: dict[str, FormatStats]
    strength: dict[str, float]  # 태그 → 제주 강점비
    jeju_by_month: dict[int, int]
    trend_source: str = "문체부 지역축제 2024-2026"
    jeju_source: str = "제주 축제 목록 (문체부 지역축제 2026)"
    budget_source: str = "문체부 지역축제 2026"

    @classmethod
    def from_panel(cls, panel: pd.DataFrame) -> "TrendData":
        from research.designation import attach_designation, match_designation
        from research.trends import (
            add_tags,
            jeju_festivals_by_month,
            jeju_gap,
            tag_budgets,
            tag_trends,
        )

        trends = tag_trends(panel)
        gap = jeju_gap(panel)
        budgets = tag_budgets(panel)
        tagged = add_tags(attach_designation(panel, match_designation(panel)))
        cur = tagged[(tagged["연도"] == 2026) & tagged["지정_2026"].notna()]
        formats = {}
        for fmt in FORMATS:
            row = trends.loc[fmt]
            des = cur[cur[fmt]].sort_values("지정명")
            formats[fmt] = FormatStats(
                new_count=int(row["신설수"]),
                new_lift=float(row["신설리프트"]),
                verdict=str(row["판정"]),
                jeju_count=int(gap.loc[fmt, "제주건수"]),
                budgets_krw=tuple(budgets[fmt].itertuples(index=False, name=None)),
                designated=tuple(zip(des["지정명"], des["지정_2026"], strict=True)),
                supply_signal=str(row["공급신호"]),
            )
        strength = gap["강점비"].dropna().round(2).to_dict()
        return cls(formats, strength, jeju_festivals_by_month(panel))


class Candidate(BaseModel):
    candidate_id: str
    format: FestivalFormat
    material: str
    material_category: MaterialCategory
    pairing: str  # "○" 또는 "△"
    months: list[int]  # 계절·형식·소재 조건을 모두 만족하는 월
    score: float
    parts: dict[str, float]  # 질문별 점수 (설명용)
    purpose_boosted: bool
    tourist_share_pct: float | None = None  # 카드의 관광객 관심 근거 (없으면 pending)
    existing_festivals: list[
        tuple[str, int | None]
    ] = []  # 같은 재료 기존 제주 축제, 가능한 월 우선
    interest_source: str | None = None


@dataclass
class CandidateSet:
    candidates: list[Candidate]  # 점수 내림차순, 상위 TOP_N개
    rules: AppliedRules
    notices: list[str] = field(default_factory=list)


def resolve_interest(
    interest: str | None, materials: tuple[Material, ...]
) -> tuple[list[Material], str | None]:
    """관심 소재로 재료를 고정한다. (쓸 재료 목록, 안내 문장)."""
    if not interest or not interest.strip():
        return list(materials), None
    text = interest.strip()
    named = [m for m in materials if m.name in text]
    if named:
        return named, None
    if text in CATEGORIES:
        return [m for m in materials if m.category == text], None
    notice = f"'{text}'은(는) 아직 제주 소재 목록에 없어서 재료를 고정하지 않고 추천했어요."
    return list(materials), notice


def _months(material: Material, fmt: str, season: str | None) -> list[int]:
    allowed = set(range(1, 13))
    for limit in (material.months, FORMAT_MONTHS.get(fmt), SEASON_MONTHS.get(season or "")):
        if limit:
            allowed &= set(limit)
    season_order = SEASON_MONTHS.get(season or "")
    if season_order:  # 겨울은 12, 1, 2 순서로
        return [m for m in season_order if m in allowed]
    return sorted(allowed)


def build_candidates(
    request: UserRequest,
    data: TrendData,
    materials: tuple[Material, ...] = SEED_MATERIALS,
    top_n: int = TOP_N,
) -> CandidateSet:
    usable, notice = resolve_interest(request.interest, materials)
    from_dictionary = all(m.strength is not None for m in materials)
    notices = [] if from_dictionary else [INTEREST_NOTICE]
    if notice:
        notices.append(notice)
    fixed = request.interest is not None and notice is None
    boosted = PURPOSE_BOOST.get(request.purpose or "", ())

    max_lift = max(s.new_lift for s in data.formats.values()) or 1
    max_new = max(s.new_count for s in data.formats.values()) or 1
    strengths = [data.strength.get(m.strength_tag) for m in materials if m.strength_tag]
    max_strength = max((s for s in strengths if s), default=1)

    categories = {m.category for m in usable}
    passed = [f for f in FORMATS if any(PAIRING[f][c] != "✕" for c in categories)]
    season = SEASON_MONTHS.get(request.season or "")
    season_excluded = [
        f
        for f in FORMATS
        if season and f in FORMAT_MONTHS and not set(FORMAT_MONTHS[f]) & set(season)
    ]
    off_season: set[str] = set()
    out = []
    for fmt in FORMATS:
        stats = data.formats[fmt]
        trend = (stats.new_lift / max_lift + stats.new_count / max_new) / 2
        gap = 1 / (1 + stats.jeju_count)
        for m in usable:
            mark = PAIRING[fmt][m.category]
            if mark == "✕":
                continue
            if fmt in season_excluded:
                continue
            months = _months(m, fmt, request.season)
            if not months:
                off_season.add(m.name)
                continue
            if m.strength is not None:
                interest = m.strength
            else:
                s = data.strength.get(m.strength_tag) if m.strength_tag else None
                interest = s / max_strength if s else NEUTRAL_INTEREST
            score = (trend + gap + interest) / 3
            if mark == "△":
                score *= TRIANGLE_FACTOR
            if fmt in boosted:
                score += PURPOSE_BONUS
            out.append(Candidate(
                candidate_id="", format=fmt, material=m.name, material_category=m.category,
                pairing=mark, months=months, score=round(score, 4),
                parts={"trend": round(trend, 4), "jeju_gap": round(gap, 4),
                       "visitor_interest": round(interest, 4)},
                purpose_boosted=fmt in boosted,
                tourist_share_pct=m.tourist_share_pct,
                existing_festivals=_pick_existing(m.existing_festivals, months),
                interest_source=DICTIONARY_SOURCE if m.tourist_share_pct is not None else None,
            ))  # fmt: skip
    if from_dictionary and any(c.tourist_share_pct is None for c in out):
        notices.append(PENDING_INTEREST_NOTICE)
    skipped = sorted(off_season - {c.material for c in out})
    if skipped:
        notices.append(f"입력한 계절에 맞지 않아 뺀 재료: {', '.join(skipped)}")
    out.sort(key=lambda c: (-c.score, FORMATS.index(c.format), c.material))
    top = [
        c.model_copy(update={"candidate_id": f"cand_{i:02d}"})
        for i, c in enumerate(_cap_repeats(out, top_n), 1)
    ]
    rules = AppliedRules(
        material_category=usable[0].category if fixed and len(categories) == 1 else None,
        pairing_passed=[f for f in passed if f not in season_excluded],
        season_excluded=season_excluded,
        purpose_boosted=list(boosted),
    )
    return CandidateSet(top, rules, notices)


def _cap_repeats(ordered: list[Candidate], top_n: int, cap: int = MAX_REPEAT) -> list[Candidate]:
    """점수 순서를 지키되 같은 형식·같은 재료가 cap개를 넘지 않게 top_n개를 고른다.

    재료를 고정하지 않았을 때 한두 재료가 상위를 다 차지하지 않게 한다. 모자라면 남은 순서대로 채운다.
    """
    formats: dict[str, int] = {}
    materials: dict[str, int] = {}
    chosen, rest = [], []
    for c in ordered:
        if formats.get(c.format, 0) < cap and materials.get(c.material, 0) < cap:
            chosen.append(c)
            formats[c.format] = formats.get(c.format, 0) + 1
            materials[c.material] = materials.get(c.material, 0) + 1
        else:
            rest.append(c)
    picked = (chosen + rest)[:top_n]
    return sorted(picked, key=ordered.index)


def pick_diverse(candidates: list[Candidate], k: int = IDEA_COUNT) -> list[Candidate]:
    """LLM 없이 고를 때(데모·대체 경로): 점수 순으로 형식이 겹치지 않게, 되도록 재료도 다르게 k개."""
    picked: list[Candidate] = []
    for need_new_material in (True, False):
        for c in candidates:
            if len(picked) == k:
                return picked
            if c in picked or any(c.format == p.format for p in picked):
                continue
            if need_new_material and any(c.material == p.material for p in picked):
                continue
            picked.append(c)
    return picked


def _recommended_months(months: list[int], data: TrendData) -> list[int]:
    """조건이 연중이면(12개월) 제주 축제가 적은 달 3개를 고른다. 외지인 데이터가 오면 바꾼다."""
    if len(months) < 12:
        return months
    ranked = sorted(months, key=lambda m: (data.jeju_by_month.get(m, 0), m))
    return sorted(ranked[:3])


def _pick_existing(
    festivals: tuple[tuple[str, int | None], ...], months: list[int]
) -> list[tuple[str, int | None]]:
    """후보의 가능한 월에 열리는 축제를 먼저, 그다음 월 순서로 최대 MAX_EXISTING개."""
    ranked = sorted(festivals, key=lambda f: (f[1] not in months, f[1] or 99, f[0]))
    return list(ranked[:MAX_EXISTING])


def _visitor_evidence(candidate: Candidate) -> VisitorInterestEvidence:
    if candidate.tourist_share_pct is None:
        return VisitorInterestEvidence(source="와이파이 장소별 방문자별 사용량", status="pending")
    return VisitorInterestEvidence(
        value=candidate.tourist_share_pct,
        metric="관련 장소 관광 사용량 비중(%)",
        source=candidate.interest_source or DICTIONARY_SOURCE,
    )


def materials_from_dictionary(d: pd.DataFrame) -> tuple[Material, ...]:
    """research.materials의 사전 표 → Material 목록."""
    out = []
    for r in d.itertuples(index=False):
        months = (
            tuple(int(m) for m in str(r.months).split("|"))
            if str(r.months) not in ("", "nan")
            else None
        )
        share = None if pd.isna(r.tourist_share_pct) else float(r.tourist_share_pct)
        raw = getattr(r, "existing_festivals", "[]")
        items = json.loads(raw) if isinstance(raw, str) and raw.startswith("[") else []
        fests = tuple((f["name"], f.get("month")) for f in items)
        out.append(Material(
            name=r.material, category=r.category, months=months,
            strength=float(r.strength), tourist_share_pct=share, existing_festivals=fests,
        ))  # fmt: skip
    return tuple(out)


def load_materials(path=None) -> tuple[Material, ...]:
    """저장된 제주 소재 사전을 읽는다. 없으면 FileNotFoundError."""
    from research.materials import MATERIALS_PATH

    path = MATERIALS_PATH if path is None else path
    return materials_from_dictionary(pd.read_csv(path, dtype={"months": str}))


def _median(values: list[int]) -> int | None:
    return int(pd.Series(values).median()) if values else None


def build_card(
    candidate: Candidate,
    rank: int,
    request: UserRequest,
    data: TrendData,
    *,
    title: str,
    concept: str,
    hypotheses: list[str],
    pick_reason: str | None = None,
) -> IdeaCard:
    """후보 + LLM 문장 → 아이디어 카드. 숫자 칸은 모두 여기서 채운다."""
    stats = data.formats[candidate.format]
    months = _recommended_months(candidate.months, data)
    budgets = [b for _, b in stats.budgets_krw]
    median = _median(budgets)
    limit = request.budget_max_krw
    examples = [] if limit is None else [
        BudgetExample(name=n, budget_krw=b) for n, b in stats.budgets_krw if b <= limit
    ][:3]  # fmt: skip
    if request.purpose and request.purpose in PURPOSE_BOOST:
        match = "일치" if candidate.purpose_boosted else "부분 일치"
    else:
        match = None
    designated = [DesignatedFestival(name=n, grade=g) for n, g in stats.designated[:3]]
    return IdeaCard(
        idea_id=f"idea_{rank:03d}",
        rank=rank,
        score=candidate.score,
        title=title,
        concept=concept,
        format=candidate.format,
        material=candidate.material,
        material_category=candidate.material_category,
        purpose_match=match,
        pick_reason=pick_reason,
        evidence=IdeaEvidence(
            trend=TrendEvidence(
                new_count=stats.new_count,
                new_lift=stats.new_lift,
                verdict=stats.verdict,
                interpretation=stats.interpretation[0],
                strategy=stats.interpretation[1],
                source=data.trend_source,
            ),
            jeju_gap=JejuGapEvidence(jeju_count=stats.jeju_count, source=data.jeju_source),
            visitor_interest=_visitor_evidence(candidate),
        ),
        reference=IdeaReference(
            type="성공 사례" if designated else "선점 기회", designated_festivals=designated
        ),
        timing=IdeaTiming(
            recommended_months=months,
            jeju_festivals_in_month=sum(data.jeju_by_month.get(m, 0) for m in months),
            sources=[data.jeju_source],
        ),
        budget=IdeaBudget(
            input_krw=limit,
            format_median_krw=median,
            scale="소규모 버전" if limit is not None and median and limit < median else "기본",
            small_examples=examples,
            source=data.budget_source,
        ),
        hypotheses=hypotheses,
        existing_jeju_festivals=[
            ExistingFestival(name=n, month=m) for n, m in candidate.existing_festivals
        ],
    )
