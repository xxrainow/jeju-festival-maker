"""Shared contracts v2 (초안): 트렌드 기반 아이디어 카드 + 확인·수정 루프."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

Season = Literal["봄", "여름", "가을", "겨울"]

# 포맷-소재 궁합표의 행 (전국 상승 형식 8개)
FestivalFormat = Literal[
    "여름·물놀이",
    "시장·상권",
    "정원·가드닝",
    "푸드·디저트",
    "맥주·주류",
    "도심·거리·골목",
    "야간·빛·드론",
    "영화·책·아트",
]

# 포맷-소재 궁합표의 열
MaterialCategory = Literal["자연", "농산물", "수산물", "문화·생활", "경관"]

DataStatus = Literal["ready", "pending"]  # pending: 데이터 대기, value는 null

CheckName = Literal["check_timing", "check_venue", "check_target", "check_risk", "check_budget"]
CheckStatus = Literal["pass", "conditional", "fail", "pending"]

# 검증 루프가 바꿀 수 있는 칸. format, material은 아이디어의 핵심이라 바꾸지 않는다
EditableField = Literal["timing.recommended_months", "venue", "budget.scale", "programs"]


# ---------- 1. 사용자 입력 ----------


class UserRequest(BaseModel):
    """모든 항목이 선택. 비어 있으면 데이터가 추천한다."""

    region: str | None = None  # 읍면동 이름 (예: "제주시 애월읍"). 없으면 제주 전역
    purpose: str | None = None  # 없으면 형식 가산점 없음
    interest: str | None = None  # 관심 소재. 있으면 재료 고정
    budget_max_krw: int | None = Field(default=None, gt=0)
    season: Season | None = None  # 거르는 조건 (점수 아님)
    target: str | None = None  # 예: "가족"


# ---------- 2. 아이디어 카드 ----------


class TrendEvidence(BaseModel):
    """질문 1. 요즘 뜨는 형식인가?"""

    new_count: int | None = None  # 2023년 이후 신설 축제 수
    new_lift: float | None = None  # 신설리프트
    verdict: str | None = None  # 판정 (확실한 상승 / 관찰 대상 / 정체 / 성숙·감소)
    interpretation: str | None = None  # 공급 신호 × 지정 사례 해석 (기획서 4절)
    strategy: str | None = None  # 해석에 따른 전략 (예: "먼저 자리 잡기")
    source: str  # 예: "문체부 지역축제 2024-2026"
    status: DataStatus = "ready"


class JejuGapEvidence(BaseModel):
    """질문 2. 제주에 없는 형식인가?"""

    jeju_count: int | None = None  # 같은 형식의 제주 축제 수
    source: str
    status: DataStatus = "ready"


class VisitorInterestEvidence(BaseModel):
    """질문 3. 관광객이 좋아하는 제주 재료인가?"""

    value: float | None = None
    metric: str | None = None  # 값의 뜻 (예: "관련 장소 관광객 비중(%)"). 정해지면 채운다
    source: str
    status: DataStatus = "ready"


class IdeaEvidence(BaseModel):
    trend: TrendEvidence
    jeju_gap: JejuGapEvidence
    visitor_interest: VisitorInterestEvidence


class DesignatedFestival(BaseModel):
    name: str
    grade: Literal["문화관광", "명예", "예비"]


class IdeaReference(BaseModel):
    type: Literal["성공 사례", "선점 기회"]
    designated_festivals: list[DesignatedFestival] = Field(default_factory=list)

    @model_validator(mode="after")
    def type_matches_list(self):
        if (self.type == "성공 사례") != bool(self.designated_festivals):
            raise ValueError("성공 사례는 지정 축제가 1개 이상, 선점 기회는 0개여야 한다")
        return self


class IdeaTiming(BaseModel):
    recommended_months: list[int] = Field(min_length=1)
    jeju_festivals_in_month: int | None = None  # 추천 월들의 제주 축제 수 합계
    outsider_visitors: float | None = None  # 유동인구가 오면 채움
    sources: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def months_in_range(self):
        if any(not 1 <= m <= 12 for m in self.recommended_months):
            raise ValueError("recommended_months는 1~12만 쓴다")
        return self


class BudgetExample(BaseModel):
    name: str
    budget_krw: int = Field(gt=0)


class IdeaBudget(BaseModel):
    input_krw: int | None = None  # 사용자 입력 예산. 미정이면 null
    format_median_krw: int | None = None  # 같은 형식 예산 중앙값
    scale: Literal["기본", "소규모 버전"]
    small_examples: list[BudgetExample] = Field(default_factory=list)
    source: str = "문체부 지역축제 2026"


class ExistingFestival(BaseModel):
    """같은 재료의 기존 제주 축제. 겹침 판정은 ④ check_risk가 하고, 카드에는 참고로만 보여준다."""

    name: str
    month: int | None = None
    source: str = "제주 축제 (문체부 지역축제 2024-2026, 전국문화축제표준데이터)"


class VenueCandidate(BaseModel):
    name: str
    admin_area: str  # 행정동·읍면 (예: "제주시 애월읍")
    reason: str | None = None  # check_venue가 고른 이유 (숫자는 CheckResult.evidence에)


class IdeaCard(BaseModel):
    idea_id: str  # 코드가 정함
    rank: int = Field(ge=1)  # 코드가 정함, 화면 비표시
    score: float | None = None  # 코드가 정함, 화면 비표시
    title: str  # LLM
    concept: str  # LLM, 한 줄
    format: FestivalFormat  # 코드
    material: str  # 코드 (제주 소재 사전의 소재명)
    material_category: MaterialCategory  # 코드
    purpose_match: Literal["일치", "부분 일치", "불일치"] | None = None  # purpose 없으면 null
    pick_reason: str | None = None  # LLM이 3개 중 하나로 고른 이유 한 줄
    evidence: IdeaEvidence
    reference: IdeaReference
    timing: IdeaTiming
    budget: IdeaBudget
    hypotheses: list[str] = Field(min_length=1)  # ④ 검증으로 넘김
    existing_jeju_festivals: list[ExistingFestival] = Field(default_factory=list)  # 코드, 최대 3개
    # 아래 둘은 아이디어 단계에서는 비어 있고 ④ 검증·수정에서 채운다
    venue: list[VenueCandidate] = Field(default_factory=list)
    programs: list[str] = Field(default_factory=list)
    status: Literal["unreviewed", "confirmed"] = "unreviewed"  # confirmed: 사용자가 "이대로 진행"


class AppliedRules(BaseModel):
    """입력 조건이 후보를 어떻게 걸렀는지. 화면의 "입력 조건 요약"에 쓴다."""

    material_category: MaterialCategory | None = None  # interest가 있을 때만
    pairing_passed: list[FestivalFormat] = Field(default_factory=list)
    season_excluded: list[FestivalFormat] = Field(default_factory=list)
    purpose_boosted: list[FestivalFormat] = Field(default_factory=list)


class IdeaProposal(BaseModel):
    """아이디어 화면 한 묶음 (A → B)."""

    input: UserRequest
    applied_rules: AppliedRules
    ideas: list[IdeaCard] = Field(min_length=3, max_length=3)
    is_demo: bool = False
    notices: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ideas_are_distinct(self):
        ids = [i.idea_id for i in self.ideas]
        if len(set(ids)) != len(ids):
            raise ValueError("idea_id가 겹친다")
        if sorted(i.rank for i in self.ideas) != [1, 2, 3]:
            raise ValueError("rank는 1, 2, 3이어야 한다")
        return self


# ---------- 3. 확인·수정 루프 ----------


class Suggestion(BaseModel):
    field: EditableField
    value: Any
    why: str


class CheckResult(BaseModel):
    """확인 도구 5개의 공통 출력. 숫자는 코드가, reason·suggestion 문장은 LLM이 쓴다."""

    check: CheckName
    status: CheckStatus
    evidence: dict[str, Any] = Field(default_factory=dict)  # 도구별 숫자·목록. 없으면 null
    sources: list[str] = Field(default_factory=list)  # 데이터명 + 기간
    reason: str
    suggestion: Suggestion | None = None
    is_synthetic: bool = False
    warnings: list[str] = Field(default_factory=list)  # 데이터 한계·주의점

    @model_validator(mode="after")
    def pass_has_no_suggestion(self):
        if self.status in {"pass", "pending"} and self.suggestion is not None:
            raise ValueError("pass, pending 결과에는 suggestion을 넣지 않는다")
        return self


class IdeaChange(BaseModel):
    field: EditableField
    before: Any
    after: Any
    why: str  # 사용자 확인 화면의 "바뀐 점과 이유"


class CheckRound(BaseModel):
    round: int = Field(ge=1, le=4)  # 1 = 처음 확인, 2~4 = 고친 뒤 재확인
    results: list[CheckResult]
    changes: list[IdeaChange] = Field(default_factory=list)  # 이 라운드 결과로 고친 것


class VerificationRun(BaseModel):
    """선택한 아이디어 1개의 검증·수정 기록 (A → B 화면)."""

    original: IdeaCard
    final: IdeaCard
    rounds: list[CheckRound] = Field(min_length=1, max_length=4)
    outcome: Literal["ready_for_approval", "needs_other_idea"]
    # ready_for_approval: fail 없음 (pending은 실패로 세지 않음) → 사용자 확인 화면
    # needs_other_idea: 3번 고치고 다시 확인해도 fail 남음 → 다른 아이디어 선택 제안

    @model_validator(mode="after")
    def core_unchanged(self):
        if (self.original.format, self.original.material) != (
            self.final.format,
            self.final.material,
        ):
            raise ValueError("format, material은 검증 루프에서 바꿀 수 없다")
        if self.original.idea_id != self.final.idea_id:
            raise ValueError("idea_id가 바뀌었다")
        last_fails = [r for r in self.rounds[-1].results if r.status == "fail"]
        if (self.outcome == "ready_for_approval") == bool(last_fails):
            raise ValueError("outcome과 마지막 라운드의 fail 여부가 맞지 않는다")
        return self


# ---------- 4. 기획안 (설계 기획서 9-4 기획서 구성, 9-5 KPI 성공 기준표) ----------
# CLAUDE.md 5절 "추가 예정": 프로그램, 장소, 예산, 가정, 미확인 사항, 확정 상태, 근거

UNCONFIRMED = "미확인"
PlanStatus = Literal["draft", "approved"]  # approved: 사용자가 최종 승인 (그 뒤에만 홍보물 생성)

# LLM이 문장을 쓰는 항목 (9-4 기본 항목 중 문장형). 나머지 항목은 코드가 입력에서 채운다
PLAN_TEXT_SECTIONS: tuple[tuple[str, str], ...] = (
    ("background", "추진 배경·필요성"),
    ("concept", "기본 컨셉"),
    ("promotion", "홍보 계획"),
    ("operation", "운영 계획"),
    ("risk", "위험 관리"),
    ("expected", "기대효과"),
)
PlanTextKey = Literal["background", "concept", "promotion", "operation", "risk", "expected"]


class PlanSection(BaseModel):
    key: PlanTextKey
    title: str
    body: str  # LLM 문장. 숫자는 입력에 있는 값만 (코드가 검사)


class PlanOverview(BaseModel):
    """사업 개요 (9-4): 축제명, 기간, 장소, 대상, 예산, 목적. 코드가 채운다."""

    name: str
    period: str  # 추천 월 + 정확한 날짜 미확인 (예: "11월 중 (날짜 미확인)")
    region: str | None = None
    venue: str = UNCONFIRMED
    target: str | None = None
    budget_krw: int | None = None
    purpose: str | None = None
    organizer: str = UNCONFIRMED  # 주최·주관 (9-4: 사용자 입력)


class PlanProgram(BaseModel):
    """세부 프로그램 (9-4: LLM, 형식·재료 기반)."""

    name: str
    description: str
    is_proposal: bool = True  # Agent 제안. 운영 주체·장소 확정 전


class PrepStep(BaseModel):
    """추진 일정 (9-4: 준비 일정 템플릿). 코드가 채운다."""

    when: str  # 예: "D-90"
    task: str


class PlanBudget(BaseModel):
    """예산 계획 (9-4: 입력 예산 + check_budget 벤치마크). 항목별 금액은 사용자 입력 전까지 미확인."""

    input_krw: int | None = None
    format_median_krw: int | None = None
    scale: Literal["기본", "소규모 버전"]
    small_examples: list[BudgetExample] = Field(default_factory=list)
    items: str = UNCONFIRMED
    source: str


class KPIValue(BaseModel):
    value: float | None = None
    status: DataStatus = "pending"
    source: str


class KPITarget(BaseModel):
    range: str | None = None  # 기존 제주 축제 실제 효과로 정한 범위. 감으로 정하지 않는다
    basis: list[str] = Field(default_factory=list)  # 근거로 쓴 기존 제주 축제
    status: DataStatus = "pending"


class PlanKPI(BaseModel):
    """성공 기준표 한 줄 (9-5)."""

    metric: str  # 예: "외지인 방문 증가율"
    region: str | None = None
    formula: str
    baseline: KPIValue
    target: KPITarget
    measure_plan: str


class PlanEvidence(BaseModel):
    """데이터 출처 (9-4): 기획서에 나오는 숫자 하나와 그 출처."""

    label: str
    value: str
    source: str


class FestivalPlan(BaseModel):
    """행사 기획안 (A → B 화면, 홍보물의 입력). 9-4 항목 순서대로 내보낸다.

    코드: 개요, 추진 일정, 예산, KPI, 데이터 검증 요약(checks), 변경 이력(changes),
          참고 사례(idea.reference), 가정과 한계, 데이터 출처
    LLM: 추진 배경, 기본 컨셉, 세부 프로그램, 홍보, 운영, 위험 관리, 기대효과
    """

    plan_id: str
    version: int = Field(default=1, ge=1)
    status: PlanStatus = "draft"
    created_at: datetime
    title: str
    idea_id: str
    request: UserRequest
    idea: IdeaCard  # 검증·수정을 마친 최종 카드
    overview: PlanOverview
    sections: list[PlanSection]  # PLAN_TEXT_SECTIONS 순서
    programs: list[PlanProgram] = Field(default_factory=list)
    prep_schedule: list[PrepStep] = Field(default_factory=list)
    budget: PlanBudget
    kpis: list[PlanKPI] = Field(default_factory=list)
    checks: list[CheckResult] = Field(default_factory=list)  # 데이터 검증 결과 요약
    changes: list[IdeaChange] = Field(default_factory=list)  # 변경 이력
    assumptions: list[str] = Field(default_factory=list)  # 가정 (Agent 해석)
    unconfirmed: list[str] = Field(default_factory=list)  # 미확인 사항 (사용자 확인·입력 필요)
    limitations: list[str] = Field(default_factory=list)  # 한계 (간접 지표, 데이터 대기)
    evidence: list[PlanEvidence] = Field(default_factory=list)  # 데이터 출처
    is_synthetic: bool = False  # 가짜·합성 데이터 결과가 섞였으면 True (화면에 표시)

    @model_validator(mode="after")
    def sections_in_order(self):
        if [s.key for s in self.sections] != [k for k, _ in PLAN_TEXT_SECTIONS]:
            raise ValueError("sections는 PLAN_TEXT_SECTIONS 순서대로 6개여야 한다")
        if self.idea_id != self.idea.idea_id:
            raise ValueError("idea_id가 카드와 다르다")
        return self
