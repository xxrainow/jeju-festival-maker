"""확인 도구가 쓰는 4-11 내국인 유동인구(읍면동) 자료 찾기.

- 실데이터: data/raw/ 아래 이름에 "4-11" 또는 "유동인구(읍면동)"이 들어간 CSV (센터에서 받은 파일, 커밋 제외)
- 없으면 가짜 데이터: data/demo/flow_demo_*.csv.gz (is_synthetic=True)
검사(validate_flow)를 통과한 표만 쓴다. 오류가 있으면 None.
"""

import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw")
DEMO_DIR = Path("data/demo")
REAL_KEYS = ("4-11", "유동인구(읍면동)")
SOURCE = "4-11 내국인 유동인구(읍면동)"
SYNTHETIC_WARNING = "4-11 유동인구는 명세서 구조로 만든 가상 데이터예요. 실제 제주 인구가 아니에요."
# SKT 연령 코드 → 와이파이 연령대
AGE_BANDS = {
    "0009": "10대 미만", "1014": "10대", "1519": "10대", "2024": "20대", "2529": "20대",
    "3034": "30대", "3539": "30대", "4044": "40대", "4549": "40대", "5054": "50대",
    "5559": "50대", "6064": "60대 이상", "6569": "60대 이상", "7000": "60대 이상",
}  # fmt: skip


@dataclass
class FlowData:
    data: pd.DataFrame  # validate_flow를 거친 표 + age_band
    is_synthetic: bool
    path: Path
    period: tuple[str, str] | None

    @property
    def label(self) -> str:
        period = f" {self.period[0]}~{self.period[1]}" if self.period else ""
        return f"{SOURCE}{period}" + (" (가상 데이터)" if self.is_synthetic else "")


def find_flow_file() -> tuple[Path, bool] | None:
    def nfc(p: Path) -> str:
        return unicodedata.normalize("NFC", p.name)

    real = sorted(p for p in RAW_DIR.glob("*.csv*") if any(k in nfc(p) for k in REAL_KEYS))
    if real:
        return real[-1], False
    demo = sorted(DEMO_DIR.glob("flow_demo_*.csv*"))
    return (demo[-1], True) if demo else None


@lru_cache(maxsize=1)
def load_flow() -> FlowData | None:
    from analytics.validate_flow import validate_flow

    found = find_flow_file()
    if found is None:
        return None
    path, synthetic = found
    report = validate_flow(path)
    if report.data is None:
        return None
    data = report.data.assign(age_band=report.data["age"].map(AGE_BANDS))
    return FlowData(data, synthetic, path, report.period)
