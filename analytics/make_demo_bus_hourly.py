"""3-04 버스 정류소별 이용 현황 가상 CSV (명세서 컬럼 그대로, 4-11 가상과 같은 2025-05-12~25).

- 정류소: 허브 정류소 ID(9자리, 명세서 예시는 7자리)·이름
- 정류소 규모: 허브 정류소별 일별 이용(이용자유형별 버스정류소 이용인원, 2025-01~10 하루 평균, 이름 단위)을
  같은 이름 정류소 수로 나눔. 이용 자료가 없는 정류소는 뺀다
- 평일·주말 하루 규모와 시간대 비중: 허브 일별 시간대별 버스 승차 파일 (7개 묶음 비중을 묶음 안 시간에 똑같이 나눔)
- 이용자구분 비중: 허브 시간대 파일의 이용자 유형 비중
- 승하차유형 비중(승차 49%, 하차 45%, 환승 6%)은 가정이다. 승차 49%는 허브 시간대 파일(승차) ÷
  정류소 파일(승하차) 중앙값, 하차·환승 나눔은 근거 없음
- 인원은 기대값에서 포아송으로 뽑는다. 0명인 칸은 넣지 않는다

실제 이용이 아니므로 결과에 is_synthetic=True를 붙인다. 3-05, 3-06(개인 단위)은 쓰지 않는다.

실행: uv run python -m analytics.make_demo_bus_hourly
"""

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from analytics.bus_hourly import BANDS, band_shares, load_hub_hourly
from analytics.make_demo_traffic import DAYS, SEED, START, WEEKDAYS

OUT_PATH = Path("data/demo/bus_station_hourly_demo_20250512_20250525.csv.gz")
COLUMNS = [
    "base_date", "pt_year", "pt_month", "day_of_week", "base_hour", "bus_station_id",
    "bus_station_name", "get_on_off_type", "user_category", "pay_type", "user_count",
]  # fmt: skip
GET_ON_OFF = {"승차": 0.49, "하차": 0.45, "환승": 0.06}  # 가정 (모듈 설명 참고)


def hour_shares(shares: pd.DataFrame, day_type: str) -> np.ndarray:
    """0~23시 비중 (묶음 비중을 묶음 안 시간에 똑같이 나눔)."""
    s = shares[(shares["day_type"] == day_type) & (shares["kind"] == "시간대")].set_index("key")
    out = np.zeros(24)
    for band, hours in BANDS.items():
        out[hours] = (s.loc[band, "share"] if band in s.index else 0.0) / len(
            hours
        )  # 빠진 묶음은 0
    return out / out.sum()


def make_station_hourly(stations: pd.DataFrame, shares: pd.DataFrame, rng) -> pd.DataFrame:
    """stations: stationId, stationName, station_key, daily_users (이름 단위 하루 승하차)."""
    st = stations.dropna(subset=["daily_users"]).copy()
    st = st[st["daily_users"] > 0]
    st["daily"] = st["daily_users"] / st.groupby("station_key")["stationId"].transform("count")
    t = shares[(shares["kind"] == "시간대")]
    day_mean = t.groupby("day_type")["daily_mean"].sum()
    factor = {
        "평일": day_mean["평일"] / day_mean["전체"],
        "주말": day_mean["주말"] / day_mean["전체"],
    }
    cats = shares[shares["kind"] == "이용자 유형"].set_index("key")["share"]
    cats = cats / cats.sum()
    types = list(GET_ON_OFF)
    type_p = np.array(list(GET_ON_OFF.values()))
    frames = []
    for d in range(DAYS):
        day = START + timedelta(days=d)
        day_type = "주말" if day.weekday() >= 5 else "평일"
        hs = hour_shares(shares, day_type)
        lam = np.outer(st["daily"].to_numpy() * factor[day_type], hs)  # 정류소 × 시
        n = rng.poisson(lam)
        si, hi = np.nonzero(n)
        counts = n[si, hi]
        by_type = rng.multinomial(counts, type_p)  # 칸 × 승하차유형
        for k, kind in enumerate(types):
            m = by_type[:, k]
            keep = m > 0
            by_cat = rng.multinomial(m[keep], cats.to_numpy())
            ci, cj = np.nonzero(by_cat)
            rows = np.flatnonzero(keep)[ci]
            frames.append(
                pd.DataFrame(
                    {
                        "base_date": day.strftime("%Y%m%d"),
                        "pt_year": str(day.year),
                        "pt_month": str(day.month),
                        "day_of_week": WEEKDAYS[day.weekday()],
                        "base_hour": [f"{h:02d}" for h in hi[rows]],
                        "bus_station_id": st["stationId"].to_numpy()[si[rows]],
                        "bus_station_name": st["stationName"].to_numpy()[si[rows]],
                        "get_on_off_type": kind,
                        "user_category": cats.index.to_numpy()[cj],
                        "pay_type": "카드",
                        "user_count": by_cat[ci, cj],
                    }
                )
            )
    out = pd.concat(frames, ignore_index=True)[COLUMNS]
    return out.sort_values(["base_date", "base_hour", "bus_station_id"]).reset_index(drop=True)


def main() -> None:
    from analytics.check_venue import STATIONS_PATH
    from analytics.reference_data import reference_first

    rng = np.random.default_rng(SEED)
    shares = band_shares(load_hub_hourly())
    stations = pd.read_csv(
        reference_first(STATIONS_PATH.name, STATIONS_PATH),
        dtype={"stationId": str},
        encoding="utf-8-sig",
    )
    out = make_station_hourly(stations, shares, rng)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_PATH, index=False, encoding="utf-8-sig", compression="gzip")
    daily = out.groupby("base_date")["user_count"].sum()
    print(f"{OUT_PATH}: {OUT_PATH.stat().st_size / 1024:,.0f} KB, {len(out):,}행")
    print(f"정류소 {out['bus_station_id'].nunique():,}곳, 하루 승하차 평균 {daily.mean():,.0f}명")


if __name__ == "__main__":
    main()
