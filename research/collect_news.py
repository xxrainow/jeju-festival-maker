"""여러 검색어로 뉴스를 모아 중복을 지우고 JSON으로 저장한다.

실행: uv run python -m research.collect_news [--query 검색어 ...] [--display 10]
저장: data/processed/news/news_<수집시각>.json (커밋 제외 폴더)

검색이 안 될 때는 load_cases()로 저장해 둔 사례를 쓰고, 화면에 수집 시점을 함께 보여준다.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.settings import Settings
from research.naver_news import NewsSearchError, search_news
from schemas.contracts import FestivalCase

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "news"

DEFAULT_QUERIES = [
    "지역 특산물 축제",
    "지역 축제 체험 프로그램",
    "지역 축제 운영 성과",
]


def collect_news(
    queries: list[str],
    display: int = 10,
    *,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> dict:
    """검색어마다 검색하고 같은 URL(같은 case_id)은 하나로 합친다.

    한 검색어가 실패해도 나머지는 계속 모으고, 실패 내역은 errors에 남긴다.
    """
    cases: dict[str, FestivalCase] = {}
    queries_by_case: dict[str, list[str]] = {}
    errors = []

    for query in queries:
        try:
            found = search_news(query, display=display, settings=settings, client=client)
        except NewsSearchError as exc:
            errors.append({"query": query, "message": str(exc)})
            continue
        for case in found:
            cases.setdefault(case.case_id, case)
            hits = queries_by_case.setdefault(case.case_id, [])
            if query not in hits:
                hits.append(query)

    if not errors:
        status = "success"
    elif len(errors) < len(queries):
        status = "partial"
    else:
        status = "failed"

    return {
        "provider": "naver_news",
        "status": status,
        "collected_at": datetime.now(UTC).isoformat(),
        "queries": queries,
        "display_per_query": display,
        "case_count": len(cases),
        "cases": [case.model_dump(mode="json") for case in cases.values()],
        "queries_by_case": queries_by_case,
        "errors": errors,
    }


def save_result(result: dict, output_dir: Path = OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = output_dir / f"news_{stamp}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_cases(path: Path) -> list[FestivalCase]:
    """저장한 수집 결과에서 사례를 다시 읽는다. 계약에 맞지 않으면 ValidationError."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return [FestivalCase.model_validate(item) for item in data["cases"]]


def latest_saved(output_dir: Path = OUTPUT_DIR) -> Path | None:
    """가장 최근에 저장한 수집 결과 파일. 없으면 None."""
    files = sorted(output_dir.glob("news_*.json"))
    return files[-1] if files else None


def main() -> int:
    parser = argparse.ArgumentParser(description="네이버 뉴스 검색 결과를 JSON으로 저장합니다.")
    parser.add_argument("--query", action="append", help="검색어. 여러 번 쓸 수 있어요.")
    parser.add_argument("--display", type=int, default=10, help="검색어별 결과 수 (1~100)")
    args = parser.parse_args()

    if not 1 <= args.display <= 100:
        parser.error("--display는 1~100이어야 해요.")
    queries = list(dict.fromkeys(q.strip() for q in (args.query or DEFAULT_QUERIES) if q.strip()))
    if not queries:
        parser.error("비어 있지 않은 검색어가 필요해요.")

    result = collect_news(queries, display=args.display)
    for error in result["errors"]:
        print(f"실패: {error['query']} - {error['message']}")
    path = save_result(result)
    print(f"상태: {result['status']}, 중복 제거 후 {result['case_count']}건")
    print(f"저장 위치: {path.relative_to(PROJECT_ROOT)}")
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
