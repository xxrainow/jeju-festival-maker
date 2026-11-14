# 공통 계약 v2 제안 (초안)

새 설계 기획서(「제주 축제 기획 Agent — 설계 결정사항」, 2026-11-07)에 맞춘 `schemas/contracts.py` 변경 제안이다.
**아직 합의 전이다.** `schemas/contracts.py`는 바꾸지 않았고, B와 합의한 뒤 옮긴다 (CLAUDE.md 5절).
아래 JSON 예시는 기획서 9-1·9-2·9-3의 예시를 그대로 쓰고, 계약에 필요한 칸만 더했다.

## 0. 무엇이 바뀌나

| 지금 (v1) | 제안 (v2) | 이유 |
|---|---|---|
| `UserRequest` (`purpose` 필수) | `UserRequest` + `season`, `target`, 모든 항목 선택 | 기획서 9-1: 비어 있으면 데이터가 추천 |
| `FestivalCase` (뉴스 사례) | **삭제** | 뉴스 모듈 삭제(확정). 사례 근거는 `IdeaReference`(문화관광축제 명단)가 대신 |
| `FestivalIdea` | `IdeaCard` | 형식×재료 조합, 근거 3칸, 사례, 시기, 예산, 검증할 가설 |
| `IdeaProposal` (`agent/proposals.py`) | `IdeaProposal` (계약으로 옮김) | B 화면이 직접 읽는 모양이라 공동 계약에 둔다 |
| `AnalysisRequest`, `AnalysisResult` | `CheckResult`, `CheckRound`, `VerificationRun` | ④ 확인 도구 5개의 공통 출력과 수정 기록 |
| (없음) | 기획안·홍보물 | 그대로 "추가 예정". 검증 루프가 돌아간 뒤 합의 |

### 흐름에서 오가는 것

| 단계 | 자료 | 방향 | 함수 (예정) |
|---|---|---|---|
| 1 | `UserRequest` | B 화면 → A | 화면 폼. 한 문장 입력은 A가 LLM으로 변환 |
| 2~3 | `IdeaProposal` | A → B 화면 | `agent.proposals.propose_idea_cards(request)` |
| 4 | 고른 `IdeaCard` | B 화면 → A | `agent.verify.verify_idea(card, request, tools)` |
| 4 내부 | `CheckResult` | B 확인 도구 → A 루프 | `check_timing(card, request)` 등 5개 |
| 4 결과 | `VerificationRun` | A → B 화면 | 사용자 확인 화면 ("이대로 진행") |
| 5~6 | 기획안, 홍보물 | A ↔ B | 추후 합의 |

### 기획서와 다르게 정한 것

기획서 예시를 계약으로 옮기면서 빈 곳을 채웠다. 모두 합의 대상이다.

1. `IdeaCard.material_category` 추가: 재료를 고정하지 않으면 아이디어마다 분류가 달라, `applied_rules`에만 두면 부족하다.
2. `IdeaCard.venue`, `IdeaCard.programs` 추가: 9-3에서 루프가 바꿀 수 있는 칸인데 9-2 카드에 없었다. 아이디어 단계에서는 비워 둔다.
3. `IdeaCard.pick_reason` 추가: 5절 "고른 이유를 한 줄씩 쓴다"를 담을 칸.
4. 출처 칸 추가: `IdeaTiming.sources`, `IdeaBudget.source`, `CheckResult.sources`. 모든 수치에 출처를 붙인다는 원칙(CLAUDE.md 3절).
5. `CheckResult.is_synthetic`, `CheckResult.warnings` 추가: 기존 `AnalysisResult`에 있던 원칙을 이어받는다.
6. 수정 가능 칸 이름: 기획서의 `program` → `programs` (카드 칸 이름과 맞춤).
7. 라운드 수: 기획서 루프 의사코드는 3번째 수정 뒤 다시 확인하지 않는다. "처음 확인 1회 + 수정 후 재확인 최대 3회 = 최대 4라운드"로 정했다.
8. `purpose_match`에 `"불일치"` 추가, `purpose`가 없으면 `null`.
9. `TrendEvidence`에 `verdict`, `interpretation`, `strategy` 추가: 기획서 3절 판정과 4절 해석 틀(공급 신호 × 지정 사례)을 카드에 싣는다. 최신 정의는 `agent/draft_contracts.py` 기준.
10. `IdeaCard.existing_jeju_festivals` 추가: 같은 재료의 기존 제주 축제(이름, 월, 최대 3개). 겹침 판정은 ④ `check_risk`가 하고 카드에는 참고로 보여준다.
11. `FestivalPlan`(기획안) 추가: 설계 기획서 9-4 항목과 9-5 성공 기준표를 그대로 담는다. 항목별 JSON 칸과 채우는 곳(코드·LLM)은 설계 기획서 9-6절.

## 1. 모델 정의 (제안 코드)

합의 전까지 이 코드는 `agent/draft_contracts.py`에 두고 A 코드(`agent/idea_gen.py`, `agent/verify.py`)가 쓴다.
합의되면 `schemas/contracts.py`로 옮기고 import만 바꾼다.

```python
"""Shared contracts v2 (초안): 트렌드 기반 아이디어 카드 + 확인·수정 루프."""

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
        if (self.original.format, self.original.material) != (self.final.format, self.final.material):
            raise ValueError("format, material은 검증 루프에서 바꿀 수 없다")
        if self.original.idea_id != self.final.idea_id:
            raise ValueError("idea_id가 바뀌었다")
        last_fails = [r for r in self.rounds[-1].results if r.status == "fail"]
        if (self.outcome == "ready_for_approval") == bool(last_fails):
            raise ValueError("outcome과 마지막 라운드의 fail 여부가 맞지 않는다")
        return self
```

## 2. `UserRequest` — 사용자 입력 (B 화면 → A)

기획서 9-1 예시:

```json
{
  "region": "제주시 애월읍",
  "purpose": "지역 상권 활성화",
  "interest": "감귤",
  "budget_max_krw": 10000000,
  "season": "겨울",
  "target": "가족"
}
```

아무것도 정하지 않은 경우 (v1과 달리 `purpose`도 비워도 된다):

```json
{
  "region": null,
  "purpose": null,
  "interest": null,
  "budget_max_krw": null,
  "season": null,
  "target": null
}
```

| 필드 | 쓰이는 곳 | 비어 있을 때 |
|---|---|---|
| `region` | 아이디어 재료·장소 범위, ④ 장소 | 제주 전역 |
| `purpose` | 형식 가산점, 기획서 KPI | 가산점 없음, `purpose_match`는 `null` |
| `interest` | 재료 고정 → 같은 재료 × 다른 형식 3개 | 재료도 점수로 추천 |
| `budget_max_krw` | 카드 예산 비교, ④ 규모 | 형식 예산 중앙값 기준 |
| `season` | 그 계절에 안 되는 형식 제외 (점수 아님) | 카드에 추천 시기만 표시 |
| `target` | 카드 대상, ④ 대상 확인 | 데이터가 추천 |

- `season`: `"봄"`, `"여름"`, `"가을"`, `"겨울"` 중 하나
- 화면 목적 선택지의 "아직 미정"은 `null`로 보낸다

## 3. `IdeaProposal` — 아이디어 화면 한 묶음 (A → B 화면)

기획서 9-2 예시에 `material_category`, `pick_reason`, `is_demo`, `notices`를 더한 것:

```json
{
  "input": {
    "region": "제주시 애월읍",
    "purpose": "지역 상권 활성화",
    "interest": "감귤",
    "budget_max_krw": 10000000,
    "season": "겨울",
    "target": "가족"
  },
  "applied_rules": {
    "material_category": "농산물",
    "pairing_passed": [
      "시장·상권",
      "푸드·디저트",
      "정원·가드닝",
      "맥주·주류"
    ],
    "season_excluded": [
      "여름·물놀이"
    ],
    "purpose_boosted": [
      "시장·상권",
      "푸드·디저트",
      "도심·거리·골목"
    ]
  },
  "ideas": [
    {
      "idea_id": "idea_001",
      "rank": 1,
      "score": null,
      "title": "애월 감귤 로컬 마켓",
      "concept": "수확철 감귤과 지역 가게가 함께 여는 주말 마켓",
      "format": "시장·상권",
      "material": "감귤",
      "material_category": "농산물",
      "purpose_match": "일치",
      "pick_reason": "상권 활성화 목적과 가장 직접 맞고, 제주에 같은 형식 축제가 없다",
      "evidence": {
        "trend": {
          "new_count": 16,
          "new_lift": 3.6,
          "source": "문체부 지역축제 2024-2026",
          "status": "ready"
        },
        "jeju_gap": {
          "jeju_count": 0,
          "source": "제주 축제 목록 (문체부 2024-2026 + 전국문화축제표준데이터)",
          "status": "ready"
        },
        "visitor_interest": {
          "value": null,
          "metric": null,
          "source": "와이파이 AP별 이용 현황",
          "status": "pending"
        }
      },
      "reference": {
        "type": "선점 기회",
        "designated_festivals": []
      },
      "timing": {
        "recommended_months": [
          12
        ],
        "jeju_festivals_in_month": 1,
        "outsider_visitors": null,
        "sources": [
          "제주 축제 목록 (문체부 2026)"
        ]
      },
      "budget": {
        "input_krw": 10000000,
        "format_median_krw": 60000000,
        "scale": "소규모 버전",
        "small_examples": [
          {
            "name": "나전역 야시장 야밤바",
            "budget_krw": 5000000
          }
        ],
        "source": "문체부 지역축제 2026"
      },
      "hypotheses": [
        "12월 애월읍 외지인 방문이 충분하다",
        "후보 장소 근처에 버스 접근성이 있다"
      ],
      "venue": [],
      "programs": [],
      "status": "unreviewed"
    },
    {
      "idea_id": "idea_002",
      "rank": 2,
      "score": null,
      "title": "감귤 디저트 페스타",
      "concept": "애월 카페·베이커리가 감귤 메뉴로 참여",
      "format": "푸드·디저트",
      "material": "감귤",
      "material_category": "농산물",
      "purpose_match": "일치",
      "pick_reason": "마켓과 달리 카페·베이커리가 주체라 참여 방식이 다르다",
      "evidence": {
        "trend": {
          "new_count": 22,
          "new_lift": 2.8,
          "source": "문체부 지역축제 2024-2026",
          "status": "ready"
        },
        "jeju_gap": {
          "jeju_count": 0,
          "source": "제주 축제 목록 (문체부 2024-2026 + 전국문화축제표준데이터)",
          "status": "ready"
        },
        "visitor_interest": {
          "value": null,
          "metric": null,
          "source": "와이파이 AP별 이용 현황",
          "status": "pending"
        }
      },
      "reference": {
        "type": "성공 사례",
        "designated_festivals": [
          {
            "name": "강릉커피축제",
            "grade": "문화관광"
          },
          {
            "name": "김천김밥축제",
            "grade": "예비"
          }
        ]
      },
      "timing": {
        "recommended_months": [
          12
        ],
        "jeju_festivals_in_month": 1,
        "outsider_visitors": null,
        "sources": [
          "제주 축제 목록 (문체부 2026)"
        ]
      },
      "budget": {
        "input_krw": 10000000,
        "format_median_krw": 278000000,
        "scale": "소규모 버전",
        "small_examples": [],
        "source": "문체부 지역축제 2026"
      },
      "hypotheses": [
        "관광객의 디저트·카페 소비가 많다",
        "참여 가능한 가게가 충분하다"
      ],
      "venue": [],
      "programs": [],
      "status": "unreviewed"
    },
    {
      "idea_id": "idea_003",
      "rank": 3,
      "score": null,
      "title": "귤빛 겨울정원",
      "concept": "감귤밭을 정원처럼 꾸민 가족 산책 축제",
      "format": "정원·가드닝",
      "material": "감귤",
      "material_category": "농산물",
      "purpose_match": "부분 일치",
      "pick_reason": "앞의 둘과 달리 체류형 산책이라 가족 대상에 맞는다",
      "evidence": {
        "trend": {
          "new_count": 10,
          "new_lift": 3.0,
          "source": "문체부 지역축제 2024-2026",
          "status": "ready"
        },
        "jeju_gap": {
          "jeju_count": 0,
          "source": "제주 축제 목록 (문체부 2024-2026 + 전국문화축제표준데이터)",
          "status": "ready"
        },
        "visitor_interest": {
          "value": null,
          "metric": null,
          "source": "와이파이 AP별 이용 현황",
          "status": "pending"
        }
      },
      "reference": {
        "type": "선점 기회",
        "designated_festivals": []
      },
      "timing": {
        "recommended_months": [
          12
        ],
        "jeju_festivals_in_month": 1,
        "outsider_visitors": null,
        "sources": [
          "제주 축제 목록 (문체부 2026)"
        ]
      },
      "budget": {
        "input_krw": 10000000,
        "format_median_krw": 200000000,
        "scale": "소규모 버전",
        "small_examples": [],
        "source": "문체부 지역축제 2026"
      },
      "hypotheses": [
        "12월 추위·바람이 야외 체류를 막지 않는다",
        "참여할 감귤 농가를 확보할 수 있다"
      ],
      "venue": [],
      "programs": [],
      "status": "unreviewed"
    }
  ],
  "is_demo": true,
  "notices": [
    "데모 응답이에요. 숫자는 문체부 2024~2026 실제 값이지만 관광객 관심 지표는 아직 없어요."
  ]
}
```

- 화면에는 `rank`, `score`를 보여주지 않는다. 순서에만 쓴다
- 근거 3칸 중 `status`가 `"pending"`이면 값 대신 "데이터 대기"로 표시한다
- `reference.type`이 `"성공 사례"`면 지정 축제가 1개 이상, `"선점 기회"`면 0개다 (코드가 검사)
- `budget.scale`이 `"소규모 버전"`이면 형식을 빼지 않고 규모를 줄인 안이라는 뜻이다
- 숫자(`new_count`, `new_lift`, `jeju_count`, 예산)는 모두 코드가 계산한다. LLM은 `title`, `concept`, `pick_reason`, `hypotheses`만 쓴다
- `is_demo`가 `true`면 `notices`를 빼지 않고 화면에 보여준다

## 4. `CheckResult` — 확인 도구 출력 (B 도구 → A 루프)

기획서 9-3 예시에 `sources`, `is_synthetic`, `warnings`를 더한 것:

```json
{
  "check": "check_timing",
  "status": "fail",
  "evidence": {
    "month": 12,
    "outsider_visitors_index": null,
    "strong_wind_days": null,
    "overlapping_festivals": []
  },
  "sources": [
    "내국인 유동인구(읍면동) 2025-05~",
    "일일 날씨",
    "제주 축제 목록 (문체부 2026)"
  ],
  "reason": "12월 애월읍 외지인 방문이 연평균보다 낮다",
  "suggestion": {
    "field": "timing.recommended_months",
    "value": [
      11
    ],
    "why": "감귤 수확 시작 시기"
  },
  "is_synthetic": true,
  "warnings": [
    "가상 데이터로 만든 결과예요. 실제 방문 규모가 아니에요."
  ]
}
```

데이터를 아직 못 받은 도구는 `pending`으로 돌려준다 (실패로 세지 않음):

```json
{
  "check": "check_target",
  "status": "pending",
  "evidence": {
    "target_age_share_pct": null,
    "jeju_avg_share_pct": null
  },
  "sources": [],
  "reason": "유동인구 성·연령 데이터를 아직 받지 않았어요.",
  "suggestion": null,
  "is_synthetic": false,
  "warnings": []
}
```

| `status` | 화면 | 루프 |
|---|---|---|
| `pass` | ✅ 통과 | 그대로 |
| `conditional` | ⚠️ 조건부 (예: 셔틀버스 필요) | 그대로, 기획서 위험 대응에 적음 |
| `fail` | ❌ 실패 | `suggestion`으로 고친 뒤 다시 확인 |
| `pending` | 데이터 대기 | 실패로 세지 않음 |

- 도구 5개의 이름: `check_timing`, `check_venue`, `check_target`, `check_risk`, `check_budget`
- `evidence`의 키는 도구마다 다르다. 도구별 키 목록은 B가 도구를 만들면서 이 문서에 추가한다
- `suggestion.field`는 `timing.recommended_months`, `venue`, `budget.scale`, `programs`만 쓸 수 있다
- 숫자는 도구(코드)가, `reason`과 `suggestion.why` 문장은 LLM이 쓴다

## 5. `VerificationRun` — 검증·수정 기록 (A → B 화면)

모양 (카드와 결과는 3, 4절 형식, 여기서는 줄임):

```text
{
  "original": { ...고르기 전 IdeaCard... },
  "final":    { ...고친 뒤 IdeaCard... },
  "rounds": [
    {"round": 1, "results": [ ...CheckResult 5개... ],
     "changes": [{"field": "timing.recommended_months", "before": [12], "after": [11],
                  "why": "12월 애월읍 외지인 방문이 연평균보다 낮아 감귤 수확이 시작되는 11월로 옮김"}]},
    {"round": 2, "results": [ ...CheckResult 5개, fail 없음... ], "changes": []}
  ],
  "outcome": "ready_for_approval"
}
```

- `rounds`는 1~4개: 처음 확인 1회 + 고친 뒤 재확인 최대 3회
- `outcome`: 마지막 라운드에 `fail`이 없으면 `"ready_for_approval"`(사용자 확인 화면), 남으면 `"needs_other_idea"`(다른 아이디어 선택 제안)
- `original`과 `final`의 `format`, `material`, `idea_id`가 다르면 오류 (코드가 검사)
- `changes`는 사용자 확인 화면의 "바뀐 점과 이유", 시연의 Agent 실행 기록으로 쓴다

## 6. 합의할 것

1. ~~`FestivalCase` 삭제와 `research/`~~: 뉴스 모듈 삭제로 확정. `research/`에는 문체부 트렌드 코드만 남았다.
2. **`AnalysisRequest/AnalysisResult`**: B의 `visit_pattern`이 지금 이것을 돌려준다. 확인 도구 안에서만 쓰고 계약에서 뺄지, 당분간 같이 둘지.
3. **확인 도구 담당**: 제안은 B가 `analytics/`에 도구 5개(숫자 계산)를, A가 `agent/`에 루프·문장·수정 적용을 만드는 것. 연결 전까지 A는 가짜 `CheckResult`로 루프를 먼저 돌린다.
4. **`jeju_festivals_in_month`**: 추천 월이 여러 개일 때 합계로 정했다. 월별로 따로 보여줘야 하면 `{월: 개수}` 모양으로 바꾼다.
5. **`visitor_interest.value`의 뜻**: 와이파이 데이터 확인 뒤 `metric`과 함께 정한다.
6. **형식 이름**: 기획서 3절 결과표("정원", "맥주")와 궁합표("정원·가드닝", "맥주·주류")의 이름이 다르다. 계약은 궁합표 이름 8개로 고정했다.
