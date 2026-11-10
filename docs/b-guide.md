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
# evidence: weather_station, strong_wind_days, heavy_rain_days, rainy_days, heat_days, weather_by_month
```

- `CheckResult.evidence`에 `months`와 함께 넣고, `sources`·`warnings`는 CheckResult의 같은 칸에 더한다
- `*_days`는 추천 월을 합친 연평균 일수(2017~2025 9년 평균). 월별 `strong_wind_years`·`heavy_rain_years`는 "9년 중 몇 년"
- 지역이 없거나 지점 연결이 없으면 값은 None이고 이유가 `warnings`에 있다. 날씨만으로 fail을 정할지는 A와 정한다
