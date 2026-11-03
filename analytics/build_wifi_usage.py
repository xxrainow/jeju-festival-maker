"""와이파이 사용량을 장소·월·방문유형별로 합쳐 data/processed/에 저장한다.

실행: uv run python -m analytics.build_wifi_usage
"""

from pathlib import Path

from analytics.loaders import WIFI_USAGE_PATH, aggregate_wifi_usage, load_wifi_usage

OUTPUT_PATH = Path("data/processed/wifi_usage_by_place_month_type.parquet")


def build(source: Path = WIFI_USAGE_PATH, output: Path = OUTPUT_PATH) -> Path:
    usage = load_wifi_usage(source)
    summary = aggregate_wifi_usage(usage)

    # 집계 전후 총합 대조
    if summary["use_amount"].sum() != usage["use_amount"].sum():
        raise ValueError("집계 전후 사용량 합계가 다릅니다")

    output.parent.mkdir(parents=True, exist_ok=True)
    summary.to_parquet(output, index=False)
    print(f"원본 {len(usage):,}행 → 집계 {len(summary):,}행")
    print(f"기간 {summary['base_year_month'].min()} ~ {summary['base_year_month'].max()}")
    print(f"방문유형 결측 {summary['visit_type'].isna().sum():,}행")
    print(f"저장: {output}")
    return output


if __name__ == "__main__":
    build()
