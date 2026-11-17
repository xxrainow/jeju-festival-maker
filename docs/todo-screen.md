# 화면 할 일 (나중에)

팀원이 `app/screen.py`, `streamlit_app.py`를 고치는 중이라 미뤄 둔 화면 작업. 판정·evidence 쪽은 끝났다.

## 1. 같은 재료 축제의 장소·거리 표시

- 대상: 시기 확인(check_timing) 결과의 주요 숫자, "바뀐 점" 이유, 위험 확인(check_risk)의 같은 재료 축제 줄
- 쓸 값: `CheckResult.evidence["overlapping_festivals"]`의 각 축제
  - `name`, `months`(개최 월), `start`·`end`(날짜를 알면), `admin_area`(행정동, 모르면 None)
  - `distance_km`: 입력 지역과의 동네 중심 거리. 같은 동네면 0, 모르면 None
  - `relation`: "같은 동네" / "가까운 동네"(10km 이내) / "먼 동네" / "장소 미확인" / "거리 미확인"
- 문장 예
  - 같은 동네: "같은 재료 축제(제26회 최남단 방어 축제)가 같은 달 서귀포시 대정읍(같은 동네)에서 열려요. 날짜를 겹치지 않게 잡으세요."
  - 가까운·먼 동네: "… 같은 달 제주시 이호동(약 12km 떨어진 곳)에서 열려요. …"
  - 장소 미확인: "… 같은 달에 열려요 (장소 미확인). …"
- "바뀐 점": 같은 동네·10km 이내 축제 때문에 fail이면 "11월에는 가까운 서귀포시 대정읍에서 같은 재료 축제가 열려요."처럼
  - 판정: `analytics/check_timing.py`의 `NEAR_FESTIVAL_KM`(10km). 그 달의 `month_checks[].status`가 fail

## 2. "가상 데이터" 표현 통일

화면에 보이는 표현을 모두 "(가상 데이터)"로 맞춘다. 코드 주석은 그대로 둔다.

| 위치 | 지금 | 바꿀 것 |
|---|---|---|
| `analytics/flow_source.py` `FlowData.label` | "(가짜 데이터)" | "(가상 데이터)" |
| `analytics/check_risk.py` 주거 밀집 경고 | "4-11 가짜 데이터로 계산했어요" | "4-11 가상 데이터로 계산했어요" |
| `analytics/flow_source.py` `SYNTHETIC_WARNING` | "가짜 데이터예요" | "가상 데이터예요" |
| `app/screen.py` `key_numbers` (위험 확인) | " [가상 데이터]" | " (가상 데이터)" |
| `analytics/check_venue.py` 야간 귀가 경고 | " [가상 데이터]" (`data_label`) | " (가상 데이터)" |
| `streamlit_app.py` 기획서 경고 | "가짜·합성 데이터" | "가상 데이터" |

- analytics 쪽 두 곳(flow_source, check_risk, check_venue)은 화면과 같이 바꿔야 문구가 맞아서 같은 때 바꾼다
- 바꾼 뒤 `tests/test_check_target_venue_risk.py`, `tests/test_app.py`의 문구 확인을 같이 고친다
