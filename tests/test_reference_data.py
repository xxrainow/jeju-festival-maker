"""앱이 읽는 가공본(analytics/reference/)만으로 장소 표가 나오는지.

허브 와이파이 AP 정보 원본(jejuhub_wifi_ap.csv)은 저장소에 없고 data/raw/에서만, 가공본을 만들 때만 쓴다.
"""

import pytest

from analytics import area_link, reference_data


def test_wifi_ap_raw_is_not_in_repository():
    assert not (reference_data.REFERENCE_DIR / "jejuhub_wifi_ap.csv").exists()
    assert area_link.WIFI_AP_PATH.parts[:2] == ("data", "raw")


def test_admin_places_need_no_wifi_ap(monkeypatch):
    def fail(*_args, **_kwargs):
        pytest.fail("앱 실행 중에 AP 원본을 읽으면 안 돼요")

    monkeypatch.setattr(area_link, "load_wifi_ap", fail)
    places = reference_data.admin_places()
    assert len(places) > 0
    assert places["admin_area"].notna().all()
    assert places["latitude"].notna().any()  # 좌표는 AP와 연결된 장소만 있음
