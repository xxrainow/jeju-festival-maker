"""센터 실데이터(data/raw/)가 명세서와 조금 달라도 앱이 멈추지 않는지.

임시 파일은 tmp_path에만 만들고, 읽기 모듈의 RAW_DIR을 tmp_path로 바꿔 끼운다 (data/raw/에 남기지 않음).
"""

from functools import cache
from pathlib import Path

import pandas as pd
import pytest

from analytics import bus_hourly, center_data, flow_source, traffic_source
from app import screen

DEMO = Path("data/demo")
FILES = {
    "4-11": [("4-11_내국인유동인구_읍면동.csv", DEMO / "flow_demo_20250512_20250525.csv.gz", "resd_pop_cnt")],
    "3-04": [("3-04_버스정류소별이용.csv", DEMO / "bus_station_hourly_demo_20250512_20250525.csv.gz", "user_count")],
    "교통": [
        ("3-10_교통량.csv", DEMO / "traffic_hourly_demo_20250512_20250525.csv.gz", "average_speed"),
        ("3-07_도로구간.csv", DEMO / "road_links_demo.csv", None),
        ("3-08_도로노드.csv", DEMO / "road_nodes_demo.csv", None),
    ],
}  # fmt: skip
LOADERS = {
    "4-11": flow_source.load_flow,
    "3-04": bus_hourly.load_station_hourly,
    "교통": traffic_source.load_traffic,
}


@pytest.fixture
def raw(tmp_path, monkeypatch):
    for mod in (flow_source, traffic_source, bus_hourly):
        monkeypatch.setattr(mod, "RAW_DIR", tmp_path)
    for load in LOADERS.values():
        load.cache_clear()
    yield tmp_path
    for load in LOADERS.values():
        load.cache_clear()


@cache
def _source(src: Path) -> pd.DataFrame:
    """가상 데이터 원본은 한 번만 읽는다 (4-11은 3,000행만)."""
    df = pd.read_csv(src, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    return df.head(3000) if "flow" in src.name or "hourly" in src.name else df


def write(kind: str, case: str, raw: Path) -> None:
    """가상 데이터와 같은 형식에서 첫 파일(4-11, 3-04, 3-10)만 case대로 바꿔 쓴다."""
    for i, (name, src, col) in enumerate(FILES[kind]):
        df = _source(src).copy()
        main = i == 0
        target = raw / name
        if main and case == "empty":
            target.write_bytes(b"")
            continue
        if main and case == "column":
            df = df.rename(columns={col: col + "_x"})
        if main and case == "date":
            df["base_date"] = pd.to_datetime(df["base_date"], format="%Y%m%d").dt.strftime(
                "%Y-%m-%d"
            )
        encoding = "cp949" if (main and case == "cp949") else "utf-8"
        df.to_csv(target, index=False, encoding=encoding)


@pytest.mark.parametrize("kind", list(FILES))
@pytest.mark.parametrize("case", ["normal", "cp949", "date"])
def test_common_format_differences_are_read_as_real_data(raw, kind, case):
    """정상·CP949·날짜 2025-05-12는 실데이터로 읽는다."""
    write(kind, case, raw)
    data = LOADERS[kind]()
    assert data is not None and data.is_synthetic is False
    assert data.fallback_reason is None
    assert screen.center_data_notices() == []


@pytest.mark.parametrize("kind", list(FILES))
@pytest.mark.parametrize("case", ["column", "empty"])
def test_unreadable_center_file_falls_back_to_synthetic_with_notice(raw, kind, case):
    """열 이름이 다르거나 빈 파일이면 멈추지 않고 가상 데이터로 대신하고 이유를 남긴다."""
    write(kind, case, raw)
    data = LOADERS[kind]()
    assert data is not None and data.is_synthetic is True
    reason = data.fallback_reason
    assert reason and ("필수" in reason or "비어 있어요" in reason)
    notices = screen.center_data_notices()
    assert notices == [f"센터 데이터를 읽지 못해 가상 데이터로 확인했어요(이유: {reason})"]


def test_reason_texts_are_plain():
    assert (
        center_data.reason_text(pd.errors.EmptyDataError("x"), "3-04") == "3-04 파일이 비어 있어요"
    )
    assert center_data.reason_text(KeyError("average_speed"), "교통") == (
        "교통 파일에 필수 열 average_speed이(가) 없어요"
    )


def test_normalize_dates_and_cp949(tmp_path):
    df = pd.DataFrame(
        {"base_date": ["2025-05-12", "2025.5.3", "20250514"], "name": ["제주", "애월", "한림"]}
    )
    assert center_data.normalize_dates(df)["base_date"].tolist() == [
        "20250512",
        "20250503",
        "20250514",
    ]
    path = tmp_path / "cp.csv"
    df.to_csv(path, index=False, encoding="cp949")
    assert center_data.read_csv_any(path, dtype=str)["name"].tolist() == ["제주", "애월", "한림"]


def test_app_shows_notice_and_keeps_going(raw, monkeypatch):
    """3-04가 빈 파일이어도 ③ 확인이 끝나고 화면 맨 위에 안내가 나온다 (AI 없이, 애월 시연)."""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("LLM_PROVIDER", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    write("3-04", "empty", raw)
    app = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
    at = AppTest.from_file(app, default_timeout=180).run()
    at.checkbox(key="use_demo").check().run()
    next(b for b in at.button if b.label == "아이디어 보기").click().run()
    next(b for b in at.button if b.label == "자세히 보기").click().run()
    next(b for b in at.button if b.label == "이 아이디어 고르기").click().run()
    assert not at.exception and not at.error and "run" in at.session_state
    notices = [w.value for w in at.warning if "센터 데이터를 읽지 못해" in w.value]
    assert notices and "3-04 버스 정류소별 이용 파일이 비어 있어요" in notices[0]


@pytest.mark.parametrize("old_file", [False, True], ids=["cached-module", "old-file"])
def test_app_keeps_going_when_notice_function_was_missing(raw, monkeypatch, old_file):
    """이전 모듈은 다시 읽고, 다시 읽어도 함수가 없으면 ③ 결과와 승인 버튼을 보여준다."""
    import importlib

    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("LLM_PROVIDER", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.delattr(screen, "center_data_notices")
    if old_file:
        original_reload = importlib.reload

        def reload_with_old_screen(module):
            return module if module is screen else original_reload(module)

        monkeypatch.setattr(importlib, "reload", reload_with_old_screen)

    app = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
    at = AppTest.from_file(app, default_timeout=180).run()
    at.checkbox(key="use_demo").check().run()
    next(b for b in at.button if b.label == "아이디어 보기").click().run()
    next(b for b in at.button if b.label == "자세히 보기").click().run()
    next(b for b in at.button if b.label == "이 아이디어 고르기").click().run()
    assert not at.exception and not at.error and "run" in at.session_state
    assert any(b.label == "이대로 진행" for b in at.button)
    assert any("일부 데이터 안내" in w.value for w in at.warning) is old_file
    if not old_file:
        assert callable(screen.center_data_notices)
