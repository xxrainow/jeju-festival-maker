"""동네별·시간대별 방문 패턴 (4-11 내국인 유동인구).

입력은 `validate_flow`가 통과시킨 표(`ValidationReport.data`)다.
- 방문인구는 "해당 시각 정각에 측정한 인원"이라 시간대를 더한 값은 서로 다른 사람 수(실인원)가 아니다
- 집계 결과에 10 미만 값이 있으면 경고한다 (센터 반출 기준)
- 가상 데이터로 낸 결과는 is_synthetic=True로 표시하고 경고와 차트 제목에도 드러낸다
"""

import uuid

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from schemas.contracts import AnalysisRequest, AnalysisResult

SMALL_VALUE = 10  # 센터 반출 기준: 이 값 미만은 반출 전에 가리거나 합쳐야 함
DAYTIME = range(10, 18)  # 10시~17시


def filter_flow(
    data: pd.DataFrame, regions: list[str] | None = None, start=None, end=None
) -> pd.DataFrame:
    """행정동(이름 또는 8자리 코드)과 기간으로 거른다."""
    df = data
    if regions:
        df = df[df["emd_nm"].isin(regions) | df["emd_cd"].isin(regions)]
    if start is not None:
        df = df[df["base_date"] >= pd.Timestamp(start)]
    if end is not None:
        df = df[df["base_date"] <= pd.Timestamp(end)]
    return df


def hourly_visits(df: pd.DataFrame) -> pd.DataFrame:
    """행정동·시간대별 방문인구 합계와 하루 평균. 열: emd_cd, emd_nm, hour, visit_pop, visit_pop_daily."""
    days = df["base_date"].nunique()
    table = (
        df.groupby(["emd_cd", "emd_nm", "time"], as_index=False)["visit_pop_cnt"]
        .sum(min_count=1)
        .rename(columns={"time": "hour", "visit_pop_cnt": "visit_pop"})
    )
    table["visit_pop_daily"] = table["visit_pop"] / days if days else None
    total = df["visit_pop_cnt"].sum()
    if abs(table["visit_pop"].sum() - total) > 1e-6 * max(1.0, total):
        raise ValueError("시간대별 합계가 원자료 합계와 다릅니다")
    return table.sort_values(["emd_nm", "hour"]).reset_index(drop=True)


def small_value_warning(table: pd.DataFrame, column: str = "visit_pop") -> str | None:
    small = table[table[column] < SMALL_VALUE]
    if small.empty:
        return None
    examples = ", ".join(f"{r.emd_nm} {r.hour}시" for r in small.head(3).itertuples())
    return (
        f"집계 결과에 {SMALL_VALUE} 미만 값이 {len(small)}개 있어요 (예: {examples}). "
        "센터 반출 기준에 따라 반출 전에 가리거나 다른 칸과 합쳐야 해요."
    )


def visit_pattern(
    data: pd.DataFrame, request: AnalysisRequest, is_synthetic: bool
) -> tuple[AnalysisResult, pd.DataFrame]:
    """요청한 동네·기간의 시간대별 방문 패턴. (결과, 행정동·시간대별 표)."""
    df = filter_flow(data, request.regions, request.start_date, request.end_date)
    warnings = []
    if is_synthetic:
        warnings.append("가상 데이터로 만든 결과예요. 실제 방문 규모가 아니에요.")
    missing = [r for r in request.regions if r not in set(df["emd_nm"]) | set(df["emd_cd"])]
    if missing:
        warnings.append(f"자료에 없는 동네가 있어요: {', '.join(missing)}")
    if df.empty:
        warnings.append("요청한 동네·기간에 해당하는 자료가 없어요.")
        return _result(request, is_synthetic, {}, warnings), pd.DataFrame()

    table = hourly_visits(df)
    by_hour = table.groupby("hour")["visit_pop"].sum()
    daily = df.groupby("base_date")["visit_pop_cnt"].sum()
    weekend = daily.index.weekday >= 5
    metrics = {
        "visit_pop_total": float(by_hour.sum()),
        "peak_hour": float(by_hour.idxmax()),
        "daytime_share_pct": float(
            by_hour[by_hour.index.isin(DAYTIME)].sum() / by_hour.sum() * 100
        ),
        "weekend_to_weekday_ratio": (
            float(daily[weekend].mean() / daily[~weekend].mean())
            if weekend.any() and (~weekend).any()
            else None
        ),
        "days": float(len(daily)),
    }
    warnings.append(
        "방문인구는 매시 정각에 잰 인원이라 시간대를 더한 값은 실제 방문자 수(실인원)가 아니에요. "
        "동네·시간대 사이 비교에만 써요."
    )
    if metrics["weekend_to_weekday_ratio"] is None:
        warnings.append("기간에 주말과 평일이 모두 있어야 주말·평일 비교를 할 수 있어요.")
    small = small_value_warning(table)
    if small:
        warnings.append(small)
    return _result(request, is_synthetic, metrics, warnings), table


def _result(request, is_synthetic, metrics, warnings) -> AnalysisResult:
    return AnalysisResult(
        result_id=f"visit_pattern-{uuid.uuid4().hex[:8]}",
        request=request,
        is_synthetic=is_synthetic,
        metrics=metrics,
        warnings=warnings,
    )


def hourly_chart(table: pd.DataFrame, is_synthetic: bool) -> go.Figure:
    """동네별 시간대 방문인구 (하루 평균) 선 그래프."""
    title = "시간대별 방문인구 (하루 평균)" + (" · 가상 데이터" if is_synthetic else "")
    fig = px.line(
        table,
        x="hour",
        y="visit_pop_daily",
        color="emd_nm",
        markers=True,
        labels={"hour": "시간", "visit_pop_daily": "방문인구 (명, 정각 측정)", "emd_nm": "동네"},
        title=title,
    )
    fig.update_xaxes(dtick=2, range=[0.5, 24.5])
    return fig
