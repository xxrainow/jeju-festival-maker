# B 기능 사용 안내 (A용)

유동인구 CSV 검증과 시간대별 방문 패턴을 Agent에서 부르는 방법이다. 모든 함수는 `analytics/`에 있다.

## 1. 흐름

```python
from datetime import date

from analytics.make_demo_flow import DEMO_PATH
from analytics.validate_flow import validate_flow
from analytics.visit_pattern import hourly_chart, visit_pattern
from schemas.contracts import AnalysisRequest

report = validate_flow(DEMO_PATH)          # 경로, bytes, Streamlit 업로드 객체 모두 가능
print(report.status)                        # "통과" / "경고" / "오류"
print(report.summary())                     # 사용자에게 보여줄 한국어 문장

if report.data is not None:                 # 오류가 없을 때만 표가 있다
    request = AnalysisRequest(
        idea_id="idea-1",
        regions=["서귀포시 성산읍", "제주시 연동"],   # 행정동명 또는 8자리 코드
        start_date=date(2025, 5, 12),
        end_date=date(2025, 5, 25),
    )
    result, table = visit_pattern(report.data, request, is_synthetic=True)
    fig = hourly_chart(table, result.is_synthetic)  # plotly Figure
```

## 2. 검증 (`validate_flow`)

- 예외를 던지지 않는다. 파일이 없거나 깨져도 `status == "오류"`와 이유 문장을 돌려준다
- `report.findings`: `Finding(level, message)` 목록. `message`는 그대로 화면·응답에 써도 되는 문장
- `report.period`(시작일, 종료일), `report.regions`(행정동명), `report.row_count`
- 오류가 있으면 `report.data`는 `None`. 분석으로 넘기지 말고 사용자에게 문장을 보여준다
- 경고는 분석은 가능하지만 사용자에게 알려야 하는 내용 (예: 연령 형식 혼합, 빈 인구 값, 빠진 시간대)

## 3. 방문 패턴 (`visit_pattern`)

`AnalysisResult` (공통 계약 그대로):

| 필드 | 내용 |
|---|---|
| `is_synthetic` | 가상 데이터면 `True`. 호출하는 쪽이 넘긴다 (데모 파일은 `True`, 센터 실데이터는 `False`) |
| `metrics["visit_pop_total"]` | 기간 방문인구 합계 (정각 측정값의 합, 실인원 아님) |
| `metrics["peak_hour"]` | 방문인구가 가장 많은 시간 (1~24) |
| `metrics["daytime_share_pct"]` | 10~17시 비중 (%) |
| `metrics["weekend_to_weekday_ratio"]` | 주말 하루 평균 ÷ 평일 하루 평균. 기간에 둘 다 없으면 `None` |
| `metrics["days"]` | 날짜 수 |
| `warnings` | 사용자에게 보여줄 주의 문장. 가상 데이터, 실인원 아님, 10 미만 값(센터 반출 기준), 없는 동네 |

`table` 열: `emd_cd`, `emd_nm`, `hour`, `visit_pop`(합계), `visit_pop_daily`(하루 평균).

## 4. 주의

- 방문인구는 매시 정각 측정값이라 시간대를 더해도 방문자 수가 아니다. 문구에 "방문자 ○명"으로 쓰지 말고 비교("낮 시간대가 ○% 많음")로 쓴다
- `warnings`는 빼지 말고 결과와 함께 보여준다 (특히 가상 데이터 표시)
- 4-11 원자료는 센터 밖으로 반출할 수 없고 가공 결과만 반출 가능하다. 10 미만 값이 있으면 반출 전에 가리거나 합친다
- 데모 파일: `data/demo/flow_demo_20250512_20250525.csv.gz` (2025-05-12~05-25, 가짜 데이터). 다시 만들기: `uv run python -m analytics.make_demo_flow`
- 데모 파일의 권역(`dstrct_se`)은 명세서에 근거가 없는 값이다. 권역 단위 분석에는 쓰지 않는다

## 5. 예산 벤치마크 (문체부 2026 지역축제 개최 계획)

```python
import pandas as pd

bench = pd.read_csv("data/processed/festival_budget_benchmark.csv")  # uv run python -m analytics.budget_benchmark 먼저
row = bench[(bench["축제 유형"] == "지역특산물") & (bench["장소 유형"] == "마을형") & (bench["기간"] == "2~3일")]
```

- 열: 축제 유형, 장소 유형, 기간(2~3일 / 4일 이상), 건수, 하위25%, 중간값, 상위25% (단위 백만원), 비고("표본 부족"이면 5건 미만)
- 기획안에는 "문체부 2026 지역축제 개최 계획 중 유사 축제 N건의 예산 중간값"처럼 건수와 출처를 함께 쓴다
- 1인당 비용은 `festival_per_capita_benchmark.csv`에 "계측 기준"과 "통신 데이터 기준"이 나란히 있다. 기본은 계측 기준이고, 둘을 섞지 않는다. 방문객 수는 주최 측 발표라 점수 계산에 쓰지 않는다
- 축제별 `memo`가 있으면(예: 전농로 왕벚꽃 축제 "거리형 행사라 통행 인원이 포함됐을 수 있음") 인용할 때 함께 쓴다
- 축제별 표(`festival_plan_2026.parquet`)의 `suspect_reasons`가 있는 축제는 사례로 인용할 때 주의 문구를 붙인다

## 6. 날씨 위험 (check_timing evidence)

```python
import pandas as pd

from analytics.weather import timing_weather_evidence

monthly = pd.read_csv("data/processed/weather_monthly_risk.csv")  # uv run python -m analytics.weather 먼저
by_dong = pd.read_csv("data/processed/weather_station_by_dong.csv")  # 지점 좌표 파일이 있어야 생김
evidence, sources, warnings = timing_weather_evidence(request.region, card.timing.recommended_months, monthly, by_dong)
# evidence: weather_station, worse_than_usual, relative_to_station, *_days, weather_by_month
```

- `CheckResult.evidence`에 `months`와 함께 넣고, `sources`·`warnings`는 CheckResult의 같은 칸에 더한다
- **주 기준은 상대 기준**: `worse_than_usual`(예: `["바람", "비"]`)은 추천 월이 같은 지점 평소보다 나쁜 항목, `relative_to_station`은 항목별 배수(1보다 크면 평소보다 나쁨). 지점끼리 비교하지 않는다
- `*_days`는 추천 월을 합친 연평균 일수(2017~2025 9년 평균)로 절대 기준 참고값이다. 14m/s 강풍일은 warnings의 "참고" 문장으로만 나온다
- 지역이 없거나 지점 연결이 없으면 값은 None이고 이유가 `warnings`에 있다. 날씨와 외지인 방문을 합친 판정은 7절 `check_timing`이 한다

## 7. 시기 확인 `check_timing` (실제 버전)

```python
from agent.fake_checks import FAKE_TOOLS
from agent.verify import verify_idea
from analytics.real_checks import REAL_TOOLS  # check_timing, check_budget

run = verify_idea(card, request, {**FAKE_TOOLS, **REAL_TOOLS})  # 나머지 3개는 가짜 그대로
```

- 먼저 표를 만든다: `uv run python -m analytics.weather` → `uv run python -m analytics.check_timing --build`. 표가 없으면 pending과 안내 문장을 돌려준다
- 입출력은 가짜 `check_timing`과 같다: `check_timing(card, request) -> CheckResult`. evidence에 가짜의 `months`, `low_months`, `outsider_visitors_index`(가짜는 None, 실제는 `{월: 지수}`)가 그대로 있다
- 더 들어가는 evidence: `outsider_index_source`, 6절 날씨 칸, `weather_rule`, `bad_weather_months`, `recommended_weeks`(예: "5월 2주차 (5/14~5/20)"), `overlapping_festivals`(이름·시작·끝·날짜 확인 여부·출처·월), `month_checks`(월별 결과·좋은 주·나쁜 주와 이유)
- 판정: fail(지수 < 0.8 또는 그 달 모든 주가 나쁨) > conditional(지수 0.8~1.0 "평소보다 약간 적은 달", 또는 같은 재료 제주 축제가 그 달에 있음) > pass(지수 1.0 이상). 지역이 없거나 그 동네 자료가 없으면 pending (suggestion 없음)
- fail 제안: 일부 달만 fail이면 그 달을 빼고, 전부 fail이면 다른 달 중 pass(없으면 conditional)이고 지수가 가장 높은 한 달 (재료 제철 안에서. 제철은 `research/reference/jeju_materials.csv`의 `months`). 고를 달이 없으면 suggestion이 None이라 루프가 멈추고 다른 아이디어로 넘어간다
- 외지인 지수는 지금 와이파이 관광 사용량(대체 지표)이라 `is_synthetic=False`이고, "사람 수가 아님" 경고가 붙는다. 4-11 가짜 데이터로 만든 지수를 쓰면 `is_synthetic=True`
- **데모 후보**: 대정읍 방어 11·12월 → 12월 바람으로 fail → 제안 "11월만" → 재확인 conditional (방어 축제 날짜 미확인). 실데이터 애월읍 감귤 12월은 지수 0.90이라 conditional이고 fail이 아니다
- 다른 판정 기준(배수, 연수)은 `BAD_RATIO`, `MIN_BAD_YEARS`

## 8. 규모 확인 `check_budget` (실제 버전)

- 7절의 `REAL_TOOLS`에 들어 있다. 따로 만들 표는 없고, A의 카드와 같은 패널(`research.trends.load_panel()`)을 읽는다
- 입출력은 가짜 `check_budget`과 같다. 입력 예산은 `request.budget_max_krw`, 없으면 `card.budget.input_krw`
- 사례 범위는 A의 `tag_budgets`와 같다: 2026년, 예산 > 0, 형식 태그. 그래서 `format_median_krw`가 카드 값과 같다 (다르면 경고)
- 판정: 예산 없음·중간값 이상 → pass / 중간값 미만이지만 그 예산 이하 같은 형식 사례 있음 → conditional("소규모 버전", 사례 최대 3개) / 사례 없음 + 카드 scale "기본" → fail, `Suggestion(field="budget.scale", value="소규모 버전")` / 사례 없음 + 이미 "소규모 버전" → conditional + "비슷한 규모 사례 없음" 경고
- 카드를 만들 때 입력 예산이 중간값보다 작으면 A가 scale을 이미 "소규모 버전"으로 두므로, 실제로는 대부분 conditional이 나온다. 계약은 바꾸지 않았고 "축소"는 "소규모 버전"을 뜻한다
- evidence: `input_krw`, `format_median_krw`, `format_q25_krw`, `scale`(확인 후 규모), `card_scale`, `small_examples`(name, budget_krw, visitors, region, year; 입력에 가까운 것부터), `basis`, `sample_count`, `visitors_estimate`(+ `_text`), `reduction_methods`
- 카드의 `small_examples`는 A 코드가 예산이 작은 것부터 3개를 고르고, `check_budget`은 입력 예산에 가까운 것부터 3개를 고른다. 화면에서 둘을 함께 보여주면 다르게 보일 수 있다
- 형식 태그 오탐 후보는 `docs/tag-review-for-a.md`
