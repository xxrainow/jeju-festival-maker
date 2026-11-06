import gzip
import io

import pandas as pd

from analytics.flow_spec import COLUMNS
from analytics.validate_flow import ERROR, PASS, WARN, validate_flow, validate_flow_frame


def row(**kw) -> dict:
    base = {
        "base_date": "20250512",
        "pt_year": "2025",
        "pt_month": "5",
        "time": "1",
        "dstrct_se": "제주시 서부",
        "emd_cd": "50110250",
        "emd_nm": "제주시 한림읍",
        "sex": "여성",
        "age": "2024",
        "resd_pop_cnt": "668.7907",
        "work_pop_cnt": "16.8249",
        "visit_pop_cnt": "168.2492",
        "resd": "제주",
    }
    return {**base, **kw}


def frame(*rows) -> pd.DataFrame:
    return pd.DataFrame(list(rows), columns=COLUMNS)


def full_day(**kw) -> pd.DataFrame:
    return frame(*[row(time=str(h), **kw) for h in range(1, 25)])


def messages(report, level) -> str:
    return " ".join(f.message for f in report.findings if f.level == level)


def test_valid_file_passes_and_shows_period_and_regions():
    report = validate_flow_frame(full_day())
    assert report.status == PASS
    assert report.period == ("2025-05-12", "2025-05-12")
    assert report.regions == ["제주시 한림읍"]
    assert report.data["time"].dtype == "int64"
    assert report.data["visit_pop_cnt"].iloc[0] == 168.2492
    assert "검사 결과: 통과" in report.summary()


def test_missing_columns_are_named():
    report = validate_flow_frame(full_day().drop(columns=["time", "resd"]))
    assert report.status == ERROR
    assert "time, resd" in messages(report, ERROR)
    assert report.data is None


def test_time_and_month_accept_leading_zero():
    df = frame(*[row(time=f"{h:02d}", pt_month="05") for h in range(1, 25)])
    assert validate_flow_frame(df).status == PASS


def test_time_out_of_range_is_error_with_line_numbers():
    df = full_day()
    df.loc[2, "time"] = "25"
    report = validate_flow_frame(df)
    assert report.status == ERROR
    assert '"25"' in messages(report, ERROR) and "줄 4" in messages(report, ERROR)


def test_age_codes_skt_0009_and_kt_are_allowed():
    for code in ["0009", "7000", "1014"]:
        assert validate_flow_frame(full_day(age=code)).status == PASS
    mixed = pd.concat([full_day(age="2024"), full_day(age="20")], ignore_index=True)
    report = validate_flow_frame(mixed)
    assert report.status == WARN
    assert "섞여" in messages(report, WARN)
    assert validate_flow_frame(full_day(age="2029")).status == ERROR


def test_codes_and_categories():
    assert validate_flow_frame(full_day(emd_cd="50110999")).status == ERROR
    assert validate_flow_frame(full_day(resd="제주도")).status == ERROR
    assert validate_flow_frame(full_day(sex="M")).status == ERROR
    assert validate_flow_frame(full_day(dstrct_se="제주시 북부")).status == ERROR
    report = validate_flow_frame(full_day(emd_nm="제주시 애월읍"))
    assert report.status == WARN  # 코드와 이름 불일치


def test_dates_and_numbers():
    assert validate_flow_frame(full_day(base_date="2025-05-12")).status == ERROR
    assert validate_flow_frame(full_day(pt_month="6")).status == WARN
    assert validate_flow_frame(full_day(visit_pop_cnt="많음")).status == ERROR
    assert validate_flow_frame(full_day(visit_pop_cnt="-1.0")).status == ERROR
    report = validate_flow_frame(full_day(work_pop_cnt=""))
    assert report.status == WARN  # 빈 인구 값은 지우지 않고 경고


def test_duplicates_and_missing_hours_warn():
    df = full_day()
    report = validate_flow_frame(pd.concat([df, df.iloc[[0]]], ignore_index=True))
    assert "겹쳐요" in messages(report, WARN)
    report = validate_flow_frame(df.iloc[:20])
    assert "24개보다 적은" in messages(report, WARN)


def test_unreadable_inputs_do_not_raise(tmp_path):
    assert validate_flow(tmp_path / "없음.csv").status == ERROR
    empty = validate_flow(b"")
    assert empty.status == ERROR and "비어" in empty.findings[0].message
    assert validate_flow(b"\xff\xfe\x00broken").status == ERROR


def test_reads_gzip_and_cp949_and_uploaded_objects(tmp_path):
    csv = full_day().to_csv(index=False)
    gz = tmp_path / "flow.csv.gz"
    gz.write_bytes(gzip.compress(csv.encode("utf-8")))
    assert validate_flow(gz).status == PASS
    assert validate_flow(csv.encode("cp949")).status == PASS
    upload = io.BytesIO(csv.encode("utf-8-sig"))
    upload.name = "flow.csv"
    assert validate_flow(upload).status == PASS
