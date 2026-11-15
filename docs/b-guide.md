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
from analytics.real_checks import REAL_TOOLS  # 확인 도구 5개 모두

run = verify_idea(card, request, {**FAKE_TOOLS, **REAL_TOOLS})  # 5개 모두 실제 버전
```

- 먼저 표를 만든다: `uv run python -m analytics.weather` → `uv run python -m analytics.real_checks --build` (확인 도구 5개 표를 한 번에, 5초쯤. `check_timing --build`만 해도 시기 표는 생김). 표가 없으면 pending과 안내 문장을 돌려준다
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

## 9. 대상 확인 `check_target` (실제 버전)

- 입력: `request.target`(대상 문구), `request.region`, `card.timing.recommended_months`
- 자료: 와이파이 장소별 사용자 현황 성·연령 (2023-01~2025-09, `data/processed/wifi_users_demographics.csv`). 4-11이 있으면 evidence `flow`에 같은 비중을 보여주고 가짜면 `flow.data_label`이 "가상 데이터". 판정은 와이파이 실데이터라 결과 `is_synthetic=False`
- 배수 = 그 동네 추천 월의 대상 비중 ÷ 제주 평균(모든 동네 장소). 1.0 이상 pass, 0.9 이상 conditional, 그 미만 fail
- 성별 대상이 있으면 성별 비중도 같은 기준으로 보고 나쁜 쪽을 쓴다
- fail 제안: 같은 동네에서 대상 배수가 1.0 이상인 다른 달 중 가장 높은 달 (재료 제철 안에서). 대상(`request.target`)은 고칠 수 있는 칸이 아니라 비중이 높은 연령대는 evidence `strong_age_groups`와 경고로만 알린다
- pending: 대상 없음, 연령대로 바꿀 수 없는 문구(예: "관광객"), 지역 없음, 그 동네 자료 없음
- 항상 붙는 경고: "와이파이 사용자 기준이라 고령층(60대 이상)이 실제보다 적게 잡힐 수 있어요."

대상 문구 → 연령대 규칙 (`analytics/check_target.py`의 `TARGET_RULES`, 여러 개가 걸리면 합침)

| 문구 | 연령대 |
|---|---|
| 가족, 아이, 어린이, 키즈, 유아, 부모, 자녀 | 30대, 40대, 10대 미만 |
| 청소년, 중학생, 고등학생, 10대 | 10대 |
| 청년, 대학생, MZ, 젊은, 2030 | 20대, 30대 |
| 중장년, 중년, 장년, 4050 | 40대, 50대 |
| 어르신, 노인, 시니어, 고령, 노년, 실버 | 60대 이상 |
| "20~30대"처럼 범위 | 범위 안 연령대 |
| "40대"처럼 하나 | 그 연령대 (60대·70대는 60대 이상) |
| 10대 미만, 영유아 | 10대 미만 |
| 여성, 여자, 엄마, 주부 / 남성, 남자, 아빠 | 성별 확인 추가 |

4-11 연령 코드(SKT)는 와이파이 연령대로 묶는다: 0009 → 10대 미만, 1014·1519 → 10대, … 6064·6569·7000 → 60대 이상 (`analytics/flow_source.py`).

## 10. 장소 확인 `check_venue` (실제 버전)

- 지역 안 와이파이 장소 중 관광 사용량 비중이 높은 곳 → 반경 `radius_m`(기본 500m, 인자로 바꿈) 안 버스 정류소 → 정류소 하루 평균 이용
- 자료 기간 2025-01~2025-10 (아이디어 단계 2023~2024와 겹치지 않게). 장소 좌표는 AP 좌표 평균
- 후보에서 빼는 장소: 정류소·충전소·올레 코스 와이파이, 공공시설 이름(A의 `EXCLUDED_PLACE`), 사용량이 제주 장소 하위 25% 미만
- evidence `candidate_places`(최대 3곳): name, admin_area, latitude, longitude, tourism_share_pct, stop_name, stop_id, stop_distance_m, stop_daily_users, stops_within_radius, good_bus
- pass: 반경 안에 하루 이용이 제주 정류소 중앙값(9명) 이상인 정류소가 있는 후보 있음 / conditional: 관광 장소는 있는데 그런 정류소가 없음 ("셔틀 필요") / fail: 지역 안 후보 없음 → `Suggestion(field="venue")`에 인접 동네 후보(`VenueCandidate` 형식) / pending: 지역 없음, 표 없음
- pass·conditional이면 카드 `venue`를 바꾸지 않는다 (루프는 fail 제안만 적용). 후보는 evidence에 있으니 화면·기획안에서 쓰면 된다
- 시간대 버스 (`analytics/bus_hourly.py`): `event_hour_usage(station_ids, hours=11~19시)`, `night_return_usage(station_ids, hours=21~23시)`가 3-04 정류소별 시간대 이용에서 후보 정류소의 하루 평균 승차를 낸다. 3-04 실데이터(`data/raw/`에 "3-04" 또는 "정류소별 이용")가 없으면 가상 데이터. evidence `event_hours`, `night_return`에 정류소별 `daily_boarding`, `share_pct`, `data_label`
- 판정은 일별 이용(실데이터)으로만 해서 결과 `is_synthetic=False`. 야간 귀가 하루 승차가 1명 미만인 후보 정류소는 "귀가 셔틀 검토" 경고
- 야간 귀가 참고 경고(실데이터): "제주 전체에서 22~24시 버스 승차는 하루의 2.2%" (허브 일별 시간대별 승차, `bus_hourly_share.csv`)
- `check_risk(..., venue_result=check_venue 결과)`로 넘기면 그 후보 장소를 정체·주거 밀집 확인에 그대로 쓴다

## 11. 위험 확인 `check_risk` (실제 버전)

- `check_risk(card, request, venue_areas=None, timing_result=None)`. 후보 장소 동네는 `venue_areas` → 카드 `venue` → `check_venue` 후보 → `request.region` 순으로 정한다
- 축제 충돌: check_timing의 `overlapping_festivals`(같은 재료·같은 달)를 그대로 써서 있으면 conditional. 같은 동네 다른 재료 축제가 check_timing 추천 주와 겹치면 경고 (날짜 미확인이면 같은 달일 때 경고)
- 주거 밀집: 4-11 거주인구(resd_pop_cnt)의 19~23시 평균이 제주 동네 평균보다 많으면 conditional "소음 민원 주의". 4-11이 가짜면 `is_synthetic=True` + 경고
- 정체: `congestion_check(points)`. 후보 장소(check_venue 후보 좌표, 없으면 카드 venue 이름으로 장소 표에서 찾음) 반경 1km 안 도로 구간의 주말 11~19시 평균 속도 ÷ 그 구간 평소 평균이 0.8 미만이면 conditional "정체 주의". 3-10·3-07·3-08 실데이터(`data/raw/`)가 없으면 가상 데이터(`data/demo/`)로 계산하고 `is_synthetic=True`. 교통 자료나 좌표가 없으면 evidence `congestion`은 pending
- 결과: 걸린 것이 있으면 conditional, 없으면 pass (fail 없음)

## 12. Git에 올린 가공본 (`analytics/reference/`, 합계 5.6MB)

- 와이파이: `wifi_usage_by_place_month_type.parquet` (2,963KB), `area_link_wifi.csv` (361KB, 장소 → 행정동·읍면 + AP 좌표)
- 허브 와이파이 AP 정보: `jejuhub_wifi_ap.csv` (738KB, `data/raw/` 사본. AP 주소·좌표. macAddress는 허브가 해시로 준 값). `analytics.area_link.load_wifi_ap()`가 먼저 읽음
- 확인 도구 표: `bus_hourly_share.csv` 5KB (허브 시간대 승차 요약), `wifi_users_demographics.csv` 694KB, `venue_places.csv` 67KB, `bus_station_daily.csv` 675KB, `dong_neighbors.csv` 8KB, `outsider_index.csv` 78KB, `jeju_festival_dates.csv` 9KB, `weather_weekly_risk.csv` 80KB, `weather_monthly_risk.csv` 12KB, `weather_station_by_dong.csv` 4KB
- `data/`가 없는 PC에서도 확인 도구 5개가 돈다 (4-11·교통 가상 데이터는 `data/demo/`에 있어 없으면 그 부분만 확인하지 않고 경고)
- 코드는 reference를 먼저 읽고, 없으면 `data/processed/`를 읽는다 (`analytics/reference_data.py`)
- 다시 만들기: `uv run python -m analytics.weather` → `uv run python -m analytics.real_checks --build` → `uv run python -m analytics.reference_data`

## 13. 교통 가상 데이터 (`data/demo/`)

- `uv run python -m analytics.make_demo_traffic`. 명세서 컬럼 그대로, 기간은 4-11 가상과 같은 2025-05-12~25
  - 3-08 도로 노드 `road_nodes_demo.csv` (850개): 허브 버스 정류소 좌표를 약 1km 격자로 솎아 놓음. 교차로명칭 자리에 정류소 이름
  - 3-07 도로 구간 `road_links_demo.csv` (2,132개): 가까운 노드 2곳씩 양방향. 링크·노드 아이디 10자리
  - 3-10 시간대별 교통량 `traffic_hourly_demo_20250512_20250525.csv.gz` (71.6만 행, 3.6MB): 제한속도 × 시간대 계수(평일 7~9·17~19시 느림, 주말 11~17시 0.85) × 잡음
- 실제 도로망·교통량이 아니다. 주말 정체를 평소의 85% 정도로만 넣어서 0.8 기준의 "정체 주의"는 거의 나오지 않는다
- 3-05, 3-06은 개인 단위라 쓰지 않는다
- 3-04 버스 정류소별 이용 현황 `bus_station_hourly_demo_20250512_20250525.csv.gz` (`uv run python -m analytics.make_demo_bus_hourly`, 70.4만 행, 5.2MB): 명세서 컬럼 그대로
  - 정류소: 허브 정류소 ID(9자리, 명세서 예시는 7자리)·이름. 이용 자료가 있는 4,019곳
  - 규모: 정류소별 일별 이용(2025-01~10 하루 평균, 이름 단위)을 같은 이름 정류소 수로 나눔
  - 평일·주말 규모와 시간대 비중: 허브 일별 시간대별 승차. 7개 묶음 비중을 묶음 안 시간에 똑같이 나눔 (22시-24시의 24시는 0시)
  - 이용자구분 비중: 허브 시간대 파일의 이용자 유형 비중
  - 승하차유형 비중 승차 49%·하차 45%·환승 6%는 가정 (승차 49%만 허브 승차 ÷ 정류소 승하차 근거, 하차·환승 나눔은 근거 없음)
  - 하루 승하차 평균 59,749명

## 14. 화면 (`streamlit_app.py`)

- 실행: `uv run streamlit run streamlit_app.py` (127.0.0.1)
- 순서는 `docs/a-guide.md`와 같다
  1. 한 문장 → `parse_request` → 입력 칸 채움(`notes`는 안내) → 사용자가 고친 뒤 "이 조건으로 확정"
  2. 카드 3장 (`propose_idea_cards`)
  3. 카드 선택 → `verify_idea(card, request, {**FAKE_TOOLS, **REAL_TOOLS})` → 5개 결과, 장소 후보 표, 바뀐 점
  4. "이대로 진행" → 기획서
- 화면 문장·표를 만드는 함수는 `app/screen.py` (Streamlit 없이 테스트)
- session_state에는 `model_dump(mode="json")`로 저장하고 `model_validate`로 읽는다. 앞 단계가 바뀌면 뒤 단계 결과를 지운다
- AI(LLM) 설정이 없을 때
  - 한 문장 입력: `RequestParseError` 문장("AI 설정이 없어요…")을 그대로 보여 주고 칸에 직접 입력
  - 카드: "데모 카드로 보기"가 기본으로 켜짐. 데모 카드는 입력과 상관없이 같은 애월 감귤 카드 3장이다 (확인 도구는 입력한 지역으로 돈다)
  - 기획서: `agent.plan`이 아직 main에 없어 "기획서 기능 준비 중" 안내. 합쳐지면 `generate_plan(run, request, approved=True)`를 부른다 (jiwoo 브랜치에서 형식 확인). 장소 후보는 지금은 확인 결과(`run`) 그대로 넘긴다
- 결과마다 `is_synthetic`이면 "🧪 가상 데이터 포함" 표시. 하단에 데이터 출처와 행정동 경계 출처(vuski/admdongkor, CC BY 4.0)
- "바뀐 점"은 `app/screen.py`의 `friendly_changes(run)`로 쉬운 말로 보여준다 (A의 `summarize`는 그대로, 원문은 "확인 기록 (회차별)" 접기 안에)
  - 제목: 필드 이름 대신 "추천 시기: 12월 → 1월", "규모: 기본 → 소규모 버전", "장소: … → …"
  - 이유: 그 변경을 제안한 확인 결과의 evidence로 쉬운 문장을 만든다 (예: "12월은 관광객이 평소보다 적고 바람이 강한 주가 많아요"). 숫자는 밑에 작게
  - 바꾼 달이 다음 확인에서 조건부면 솔직하게: "12월은 평소보다 관광객이 약간 적지만, 제철 안에서 가장 나은 달이에요" (같은 재료 축제 때문이면 날짜를 겹치지 않게 잡으라고 안내)
  - 제철은 "제철: 11·12·1월"만 보여준다. 근거 문구(팀 내부 문서)는 check_timing evidence `material_season.basis`에만 있다
  - 같은 변경을 두 확인이 함께 제안하면 한 칸에 이유를 합친다
- 확인 도구 문장에는 fail·pass 같은 영어나 evidence 같은 개발 용어를 쓰지 않는다. 표가 없을 때 명령어는 "관리자용" 경고에만
- 아이디어 카드 문장 (`app/screen.py`, A의 카드 데이터는 그대로)
  - 첫째 근거 제목은 판정별로: 확실한 상승 → "요즘 늘고 있는 축제예요 📈", 관찰 대상 → "조금씩 늘고 있는 축제예요", 정체 → "꾸준히 열리는 축제예요", 성숙·감소 → "이미 많이 열리는 축제예요"
  - 본문: "2023년 이후 새로 생겨 2026년에 열리는 {형식} 축제가 전국 {N}개예요. 새로 생긴 축제 중 이 형식의 비율이 예전부터 열던 축제보다 {X}배 높아요." (X는 소수 첫째 자리, 1 미만이면 "더 낮아요"). A의 신설리프트 = (2023년 이후 신설 중 형식 비율) ÷ (기존 중 형식 비율), 둘 다 2026년 계획에 있는 축제 기준이라 "예전보다 자주 생긴다"가 아니라 비율 비교로 쓴다
  - 둘째: 0개 "제주에는 아직 없어요", 1개 이상 "제주에도 N개 있어요". 셋째: 관광객 관심 비중 문장, 데이터 대기면 "관광객 관심은 아직 확인 중이에요"
  - 사례: 선점 기회 → "아직 전국에 대표 축제가 없어요. 먼저 시작할 기회예요", 성공 사례 → "비슷한 성공 축제: …"
  - "추천 시기: 12월 · 이 달 제주 축제 1개", 예산 "비슷한 축제는 보통 6,000만 원이 들어요. 입력한 1,000만 원으로는 작게 여는 걸 추천해요"
  - "검증할 가설" → "고르면 확인할 것", 끝 "~다"를 "~인지"로 (`check_phrase`, 규칙 밖 문장은 그대로)
  - 출처는 기관 이름을 풀어서: "문화체육관광부 지역축제 개최계획 (2024~2026)" (`plain_source`)
- 데모 카드면 카드 위 노란 경고 "AI 연결 전이라 입력과 상관없는 예시 카드예요…"와 입력과 다른 점(지역·계절·재료)
- 입력 계절과 재료 제철(A의 소재 사전 가공본)이 안 겹치면 "감귤은 11·12·1월이 제철이라 여름과 맞지 않아요. 계절이나 재료를 바꿔보세요" (막지 않음)
- 작은 숫자는 실패 이유가 된 숫자를 먼저 보여준다 (예: 대정 12월은 "날씨 나쁜 주 4/4주"가 앞, 관광객 지표가 뒤)
- 자료가 적은 지역 안내: 확인 결과 evidence의 `low_data`가 있으면 결과 위(마지막 회차 기준)와 그 변경 칸에 "이 지역은 자료가 적어 결과가 불안정할 수 있어요"
  - check_timing: 외지인 지수에 쓴 와이파이 장소 5곳 미만(`MIN_WIFI_PLACES`), 날씨 지점까지 20km 초과(`FAR_STATION_KM`)
  - check_target: 동네 와이파이 사용자가 동네 중앙값의 10% 미만(`MIN_USERS_SHARE`), 추천 월 대상 연령대 사용자 100명 미만(`MIN_TARGET_USERS`)
  - 지금 기준에 걸리는 동네는 추자면뿐 (장소 4곳, 날씨 지점 53km, 사용자 중앙값의 3%). 다음으로 적은 동네는 정방동 5.5곳, 안덕면 17.2km, 도두동 29%
- 테스트: `tests/test_app.py`가 AppTest로 한 문장부터 승인까지 누른다 (.env에 키가 있어도 AI 없이)
