"""4-11 내국인 유동인구(읍면동)_v02 형식의 가상 CSV를 만든다 (시연·개발용).

실행: uv run python -m analytics.make_demo_flow
결과: data/demo/flow_demo_20250512_20250525.csv.gz (커밋 대상, 가짜 데이터)

- 기간 2025-05-12(월) ~ 2025-05-25(일) 14일 (주말 4일). 명세의 모든 조합
  (행정동 43 × 시간 24 × 성별 2 × 연령 14 × 거주지 2)
- 시연용 패턴: 주말 방문 증가, 관광지 많은 동네는 거주지 "그외" 비율이 높음, 낮 시간대 방문 증가
- 동네 규모·관광 가중치는 후보지 비교표를 참고해 정한 가상 값이다. 실제 수치가 아니다
- 권역(dstrct_se)은 명세서에 행정동별 표가 없어 지리적으로 정한 값이다 (실데이터로 확인 필요)
"""

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from analytics.flow_spec import AGE_CODES, COLUMNS, DEMO_DISTRICT_BY_EMD, EMD_CODES, SEXES

DEMO_PATH = Path("data/demo/flow_demo_20250512_20250525.csv.gz")
START, DAYS = date(2025, 5, 12), 14
SEED = 20250512

# 상대 거주 규모 (기본 1.0)
RESIDENT_SCALE = {
    "제주시 노형동": 3.0,
    "제주시 연동": 2.5,
    "제주시 이도2동": 2.5,
    "제주시 아라동": 2.2,
    "제주시 애월읍": 2.0,
    "제주시 조천읍": 1.6,
    "제주시 한림읍": 1.4,
    "제주시 일도2동": 1.8,
    "제주시 화북동": 1.6,
    "제주시 삼양동": 1.4,
    "제주시 외도동": 1.4,
    "서귀포시 동홍동": 1.6,
    "서귀포시 대정읍": 1.4,
    "서귀포시 남원읍": 1.3,
    "서귀포시 성산읍": 1.0,
    "제주시 추자면": 0.15,
    "제주시 우도면": 0.15,
}
# 관광 가중치 0~1 (기본 0.1). 클수록 방문이 많고 "그외" 거주자 비율이 높다
TOURIST_WEIGHT = {
    "서귀포시 성산읍": 1.0,
    "서귀포시 안덕면": 0.9,
    "서귀포시 중문동": 0.9,
    "제주시 우도면": 0.9,
    "서귀포시 예래동": 0.8,
    "서귀포시 천지동": 0.7,
    "제주시 구좌읍": 0.7,
    "제주시 애월읍": 0.7,
    "서귀포시 송산동": 0.6,
    "제주시 한림읍": 0.6,
    "서귀포시 정방동": 0.5,
    "서귀포시 표선면": 0.5,
    "제주시 조천읍": 0.5,
    "제주시 건입동": 0.5,
    "제주시 용담2동": 0.5,
    "제주시 연동": 0.4,
    "제주시 봉개동": 0.4,
}
# 연령대 비중 (0009, 1014, ..., 7000)
AGE_WEIGHT = np.array([0.8, 0.5, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.0, 1.0, 0.9, 0.8, 0.7, 1.2])


def hour_profiles(hours: np.ndarray, weekend: np.ndarray) -> tuple[np.ndarray, ...]:
    """시간대별 배수: 거주(낮에 줄어듦), 근무(평일 낮), 방문(낮에 늘어남)."""
    day = np.exp(-(((hours - 14) / 4.0) ** 2))
    resident = 1.0 - 0.4 * day
    work = np.where((hours >= 9) & (hours <= 18), 1.0, 0.15) * np.where(weekend, 0.4, 1.0)
    visit = 0.2 + day
    return resident, work, visit


def build_demo(start: date = START, days: int = DAYS, seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    codes = list(EMD_CODES)
    names = [EMD_CODES[c] for c in codes]
    dates = [start + timedelta(days=i) for i in range(days)]
    shape = (len(dates), 24, len(codes), len(SEXES), len(AGE_CODES), 2)
    d, h, e, s, a, r = np.indices(shape).reshape(len(shape), -1)

    weekend = np.array([x.weekday() >= 5 for x in dates])[d]
    hours = h + 1
    scale = np.array([RESIDENT_SCALE.get(n, 1.0) for n in names])[e]
    tourism = np.array([TOURIST_WEIGHT.get(n, 0.1) for n in names])[e]
    resident_h, work_h, visit_h = hour_profiles(hours, weekend)
    base = 450 * scale * AGE_WEIGHT[a] * rng.lognormal(0, 0.15, len(d))
    outside = r == 1  # 거주지 "그외"

    resd_pop = base * resident_h * np.where(outside, 0.01, 1.0)
    work_pop = 0.25 * base * work_h * np.where(outside, 0.03, 1.0)
    # 방문: 관광지 많은 동네일수록 많고, 주말에는 관광 가중치만큼 더 늘어난다
    visit_total = (
        0.3 * base * visit_h * (1 + 3 * tourism) * np.where(weekend, 1.2 + 0.4 * tourism, 1.0)
    )
    outside_share = 0.1 + 0.6 * tourism
    visit_pop = visit_total * np.where(outside, outside_share, 1 - outside_share)

    date_str = np.array([x.strftime("%Y%m%d") for x in dates])[d]
    return pd.DataFrame(
        {
            "base_date": date_str,
            "pt_year": np.array([str(x.year) for x in dates])[d],
            "pt_month": np.array([str(x.month) for x in dates])[d],  # 명세 예시처럼 앞에 0 없음
            "time": hours.astype(str),  # 명세 예시처럼 "1"
            "dstrct_se": np.array([DEMO_DISTRICT_BY_EMD[n] for n in names])[e],
            "emd_cd": np.array(codes)[e],
            "emd_nm": np.array(names)[e],
            "sex": np.array(SEXES)[s],
            "age": np.array(AGE_CODES)[a],
            "resd_pop_cnt": np.char.mod("%.4f", resd_pop),
            "work_pop_cnt": np.char.mod("%.4f", work_pop),
            "visit_pop_cnt": np.char.mod("%.4f", visit_pop),
            "resd": np.array(["제주", "그외"])[r],
        }
    )[COLUMNS]


def main() -> None:
    df = build_demo()
    DEMO_PATH.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0: 다시 만들어도 같은 파일이 나오게
    df.to_csv(DEMO_PATH, index=False, encoding="utf-8", compression={"method": "gzip", "mtime": 0})
    print(f"{DEMO_PATH}: {len(df):,}행, {DEMO_PATH.stat().st_size / 1e6:.1f}MB")


if __name__ == "__main__":
    main()
