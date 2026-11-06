"""검색 출처(네이버, Tavily 등)가 같이 쓰는 도구."""

import hashlib
import html
import re
from datetime import date, datetime
from email.utils import parsedate_to_datetime

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def clean_text(value: str) -> str:
    """HTML 태그(<b> 등)와 HTML 문자(&quot; 등)를 지우고 공백을 정리한다."""
    return _SPACE.sub(" ", html.unescape(_TAG.sub("", value or ""))).strip()


def make_case_id(url: str) -> str:
    """같은 URL이면 출처나 수집 시점이 달라도 같은 ID가 나온다."""
    return "case_" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def parse_date(value: str | None) -> date | None:
    """RFC 822("Tue, 21 Oct 2026 09:30:00 +0900")나 ISO("2026-10-21...") 날짜를 읽는다.

    읽지 못하면 추측하지 않고 None.
    """
    value = (value or "").strip()
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).date()
    except (TypeError, ValueError, IndexError):
        pass
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None
