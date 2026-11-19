"""홍보물 (포스터 + SNS 글). 승인된 기획서(FestivalPlan)로만 만든다 (CLAUDE.md 2절 9단계).

- 기획서에서 축제 이름, 기간, 지역, 장소, 대상, 재료, 형식, 컨셉만 쓴다. 센터 데이터·집계 수치는 쓰지 않는다
- 미확인 칸은 지어내지 않고 "날짜 추후 공지", "장소 추후 공지"로 쓴다 (fixed_texts)
- 포스터: Gemini 이미지 모델로 글자 없는 배경 그림을 받고(그림 설명은 영어, 이름·기간·장소·숫자 없음),
  Pillow로 한글 문구를 얹어 1200×1600(3:4) PNG로 저장한다. 그림을 못 받으면 단색 기본 포스터
- SNS 글: A의 LLM 연결(agent.proposals.default_llm)로 인스타그램 글 3~5문장 + 해시태그 5개.
  기간·장소는 AI에게 맡기지 않고 코드가 끝에 "언제: … · 어디: …" 줄로 붙인다 (sns_info)
- 프로그램: 포스터·SNS에는 기획서 programs에 있는 프로그램만 쓴다. 없는 행사(드론 쇼 등)가 나오면 다시 생성
- 정보 일치 검사: 이름·기간·장소가 기획서와 같은지, 기획서에 없는 숫자·프로그램이 없는지
  (숫자 규칙은 agent.plan.allowed_numbers와 같음, 월 표기는 허용)

이미지 API (Gemini 공식 문서 2026-11 확인, https://ai.google.dev/gemini-api/docs/image-generation):
POST https://generativelanguage.googleapis.com/v1beta/interactions, 헤더 x-goog-api-key·Api-Revision,
본문 {"model", "input", "response_format": {"type": "image", "aspect_ratio", "image_size"}}.
그림은 응답의 output_image.data 또는 steps의 image 블록(base64). 이미지 모델은 무료 등급이 없다.
키는 오류 문장·로그에 넣지 않는다.
"""

import base64
import io
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field

from agent.draft_contracts import UNCONFIRMED, FestivalPlan

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
API_REVISION = "2026-05-20"
DEFAULT_IMAGE_MODEL = "gemini-3.1-flash-lite-image"
ASPECT_RATIO = "3:4"
IMAGE_SIZE = "1K"
POSTER_SIZE = (1200, 1600)
FONT_PATH = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "NotoSansKR-Bold.otf"
OUTPUT_DIR = Path("outputs/promo")
AI_CREDIT = "이미지: AI 생성 (Gemini)"  # AI 그림을 쓴 포스터에만 Pillow로 작게 넣는다 (글자 검사에서는 뺀다)
# 포스터 문구 한 줄 30자. 제목은 줄이지 않고 글자 크기·줄바꿈으로 맞춘다
LINE_MAX, MAX_PROGRAMS = 30, 3
TITLE_FONT_SIZES = (84, 72, 62, 54)  # 제목이 두 줄 안에 들어갈 때까지 줄인다
# 프로그램처럼 읽히는 말. 기획서 programs(이름·설명)나 축제 이름에 없으면 지어낸 프로그램으로 본다
PROGRAM_WORDS = (
    "드론", "불꽃", "폭죽", "레이저", "라이트쇼", "미디어아트", "퍼레이드", "콘서트", "버스킹",
    "공연", "노래자랑", "마술", "경품", "추첨", "푸드트럭", "플리마켓", "포토존", "쿠킹", "클래스",
    "시식", "야시장", "전시", "체험", "만들기", "투어", "대회", "경연",
)  # fmt: skip
SEASON_KO = {
    **dict.fromkeys((3, 4, 5), "봄"), **dict.fromkeys((6, 7, 8), "여름"),
    **dict.fromkeys((9, 10, 11), "가을"), **dict.fromkeys((12, 1, 2), "겨울"),
}  # fmt: skip
POSTER_ATTEMPTS = 3  # 글자 넣은 포스터: 처음 1번 + 다시 생성 2번
EXTRA_TOLERANCE = 2  # 글자 검사에서 정하지 않은 글자를 몇 자까지 봐줄지 (읽기 오차)
TEXT_FALLBACK_NOTICE = "AI가 글자를 정확히 그리지 못해 글자를 따로 얹었어요."
SNS_ATTEMPTS = 3  # 처음 1번 + 다시 생성 2번
HASHTAG_COUNT = 5

QUOTA_NOTICE = "이미지 생성은 결제 설정한 키가 필요해요. 아래 그림 설명을 AI Studio에 붙여 넣으면 직접 만들 수 있어요."
FAIL_NOTICE = (
    "배경 그림을 만들지 못해 기본 포스터로 만들었어요. 아래 그림 설명으로 직접 만들 수 있어요."
)
NO_KEY_NOTICE = "AI 설정이 없어 배경 그림 없이 기본 포스터로 만들었어요. 아래 그림 설명으로 직접 만들 수 있어요."
_QUOTA_WORDS = ("quota", "resource_exhausted", "billing", "free tier", "limit: 0", "rate limit")

# 숫자 규칙: agent.plan과 같은 정규식 (월 표기는 숫자 검사에서 뺀다)
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_MONTH = re.compile(r"(?<!\d)(?:1[0-2]|[1-9])\s*월")

# 그림 설명용 영어 (재료·형식·계절). 표에 없으면 일반 표현
MATERIAL_EN = {
    "유채꽃": "yellow canola flower fields", "벚꽃": "cherry blossoms", "수국": "hydrangeas",
    "청보리": "green barley fields", "해바라기": "sunflowers", "용천수": "clear spring water pools",
    "오름": "volcanic oreum hills", "해변": "a sandy beach", "폭포·계곡": "a waterfall and valley",
    "숲길": "a forest trail", "감귤": "tangerines and citrus orchards", "메밀": "buckwheat flowers",
    "고사리": "fresh bracken ferns", "마늘": "garlic harvest", "흑돼지": "a cozy grill feast",
    "방어": "fresh yellowtail fish and a harbor", "갈치": "silver hairtail fish and fishing boats",
    "자리돔": "small damselfish and a fishing village", "소라": "turban shells by the sea",
    "광어": "flatfish and a seaside market", "부시리": "amberjack fish and blue sea",
    "참굴비": "dried yellow croaker", "조개": "seashells on a tidal flat",
    "해녀": "haenyeo women divers in the sea", "테우": "a traditional wooden raft",
    "원담": "a stone tidal fish trap", "포구": "a small fishing harbor", "제주마": "Jeju horses",
    "들불": "a festive bonfire on a hill", "전통민속": "traditional Jeju folk culture",
    "신화·설화": "Jeju mythology motifs", "천연염색": "naturally dyed persimmon fabric",
    "일출": "a sunrise over the sea", "해넘이": "a sunset over the sea",
    "올레·돌담길": "black basalt stone walls and a walking trail",
}  # fmt: skip
FORMAT_MOOD = {
    "여름·물놀이": "bright, splashy summer water fun",
    "시장·상권": "lively local market stalls and warm string lights",
    "정원·가드닝": "a calm, lush garden",
    "푸드·디저트": "delicious desserts and food stalls",
    "맥주·주류": "relaxed outdoor drinks with friends",
    "도심·거리·골목": "a charming alley street with small shops",
    "야간·빛·드론": "glowing night lights and lanterns",
    "영화·책·아트": "an artistic, creative atmosphere",
}  # fmt: skip
SEASON_EN = {
    **dict.fromkeys((3, 4, 5), "spring"),
    **dict.fromkeys((6, 7, 8), "summer"),
    **dict.fromkeys((9, 10, 11), "autumn"),
    **dict.fromkeys((12, 1, 2), "winter"),
}
CATEGORY_COLORS = {  # 단색 기본 포스터 배경 (재료 분류)
    "자연": (46, 125, 90), "농산물": (230, 126, 34), "수산물": (31, 97, 141),
    "문화·생활": (120, 81, 60), "경관": (91, 70, 150),
}  # fmt: skip


class TextReadError(RuntimeError):
    """포스터 글자를 읽지 못함 (글자 검사를 할 수 없음)."""


class ImageQuotaError(RuntimeError):
    """이미지 모델 한도·결제 문제 (무료 키 포함)."""


class ImageGenerationError(RuntimeError):
    """그 밖의 이미지 생성 실패. 메시지에 키는 넣지 않는다."""


class AspectRatioError(ImageGenerationError):
    """aspect_ratio 값 때문에 거절됨 → 비율 없이 다시 요청한다."""


class PromoCheck(BaseModel):
    item: str
    ok: bool
    detail: str = ""


class PromoResult(BaseModel):
    """홍보물 한 벌. session_state에는 model_dump(mode="json")로 저장한다."""

    plan_id: str
    plan_version: int
    created_at: datetime
    poster_path: str
    poster_text: dict[str, str]  # title, period, place (포스터에 쓴 값)
    poster_lines: dict[str, str] = Field(default_factory=dict)  # 포스터 문구 6줄 (위치별)
    poster_mode: str = (
        "plain"  # ai_text: AI가 글자까지 그림 / overlay: 글자 없는 그림 + Pillow / plain: 단색
    )
    text_attempts: int = 0  # 글자 넣은 포스터를 만든 횟수
    text_problems: list[str] = Field(default_factory=list)  # 마지막 글자 검사에서 나온 문제
    used_ai_image: bool
    image_cropped: bool = False  # 3:4가 아니어서 1200×1600으로 잘라 씀
    image_prompt: str
    image_notice: str | None = None  # 그림을 못 받았을 때 안내
    sns_text: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    sns_notice: str | None = None  # SNS 글을 못 만들었거나 검사를 통과하지 못했을 때
    checks: list[PromoCheck] = Field(default_factory=list)
    is_synthetic: bool = False


# ---------- 기획서에서 뽑기 ----------


def _section(plan: FestivalPlan, key: str) -> str:
    return next((s.body for s in plan.sections if s.key == key), "")


def fixed_texts(plan: FestivalPlan) -> dict[str, str]:
    """포스터·SNS에 그대로 쓰는 문구. 미확인 칸은 지어내지 않는다."""
    o = plan.overview
    period = (o.period or "").strip()
    known = period.replace(f"({UNCONFIRMED})", "").replace("(날짜 미확인)", "").strip()
    if not known or known == UNCONFIRMED:
        period_text = "일정 추후 공지"
    elif "미확인" in period:
        period_text = f"{known} · 날짜 추후 공지"
    else:
        period_text = period
    if o.venue and o.venue != UNCONFIRMED:
        place_text = f"{o.region} {o.venue}".strip() if o.region else o.venue
    elif o.region:
        place_text = f"{o.region} · 장소 추후 공지"
    else:
        place_text = "장소 추후 공지"
    return {"title": o.name, "period": period_text, "place": place_text}


def sns_info(plan: FestivalPlan) -> dict[str, str]:
    """SNS 글 끝에 코드가 붙이는 언제·어디. 미확인은 "추후 공지"로 자연스럽게 쓴다."""
    o = plan.overview
    period = (o.period or "").strip()
    known = period.replace(f"({UNCONFIRMED})", "").replace("(날짜 미확인)", "").strip()
    if not known or known == UNCONFIRMED:
        when = "추후 공지"
    elif "미확인" in period:
        when = f"{known} (날짜는 추후 공지)"
    else:
        when = period
    if o.venue and o.venue != UNCONFIRMED:
        where = f"{o.region} {o.venue}".strip() if o.region else o.venue
    elif o.region:
        where = f"{o.region} (장소는 추후 공지)"
    else:
        where = "추후 공지"
    return {"when": when, "where": where, "line": f"언제: {when} · 어디: {where}"}


def season_text(plan: FestivalPlan) -> str:
    """추천 월의 계절 (첫 달 기준). 월이 없으면 빈 문자열."""
    if plan.markdown_override is not None:
        month = re.search(r"(?<!\d)(1[0-2]|[1-9])월", plan.overview.period)
        return SEASON_KO.get(int(month[1]), "") if month else ""
    months = plan.idea.timing.recommended_months
    return SEASON_KO.get(months[0], "") if months else ""


def promo_payload(plan: FestivalPlan) -> dict:
    """SNS 글에 넘기는 기획서 값. 숫자 허용 목록도 여기서 만든다.

    형식 태그(예: "야간·빛·드론")는 넘기지 않는다: 기획서에 없는 프로그램(드론 쇼 등)을 약속하게 된다.
    """
    return {
        "축제 이름": plan.overview.name,
        "지역": plan.overview.region or "",
        "계절": season_text(plan),
        "대상": plan.overview.target or "",
        "재료": plan.idea.material,
        "컨셉": _section(plan, "concept") or plan.idea.concept,
        # 이름만 넘긴다: 설명을 넘기면 긴 설명 문장을 그대로 옮긴다 (QA 2차)
        "프로그램": [p.name.strip() for p in plan.programs if p.name.strip()],
    }


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def unplanned_programs(text: str, plan: FestivalPlan) -> list[str]:
    """기획서 programs(이름·설명)와 축제 이름에 없는 프로그램 말 (예: 기획서에 없는 "드론")."""
    planned = _squash(
        " ".join([plan.overview.name, *(f"{p.name} {p.description}" for p in plan.programs)])
    )
    found = _squash(text)
    return [w for w in PROGRAM_WORDS if w in found and w not in planned]


def shorten(text: str, limit: int) -> str:
    """limit자 안으로 줄인다. 띄어쓰기에서 끊고, 없으면 글자에서 끊는다 (말줄임표는 붙이지 않는다)."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    return cut[: cut.rfind(" ")] if " " in cut[1:] else cut


def _josa_wa(word: str) -> str:
    last = word[-1] if word else ""
    has_final = "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0
    return "과" if has_final else "와"


def _clean_sentence(text: str) -> str:
    first = re.split(r"(?<=[.!?])\s", " ".join((text or "").split()))[0].rstrip(".!? ")
    for end in ("이다", "입니다", "이에요", "예요"):
        if first.endswith(end):
            return first[: -len(end)].rstrip()
    return first


def _concept_line(plan: FestivalPlan) -> str:
    """포스터 맨 위 한 줄. 문장 중간에서 자르지 않는다.

    카드 컨셉 → 기획서 컨셉 첫 문장 → 그 앞 구절(쉼표 앞) 순서로, 한 줄(30자)에 통째로 들어가고
    기획서에 없는 프로그램 말이 없는 것을 쓴다. 없으면 "방어와 함께하는 겨울 축제"처럼 짧게 만든다.
    """
    sentences = [_clean_sentence(plan.idea.concept), _clean_sentence(_section(plan, "concept"))]
    if plan.markdown_override is not None:
        sentences = [sentences[1]]  # 수정한 기획서의 컨셉을 사용한다
    candidates = [*sentences, *(s.split(",")[0].strip() for s in sentences if "," in s)]
    for text in candidates:
        if 8 <= len(text) <= LINE_MAX and not unplanned_programs(text, plan):
            return text
    material = plan.idea.material
    season = season_text(plan)
    return f"{material}{_josa_wa(material)} 함께하는 {season + ' ' if season else ''}축제"


def _closing_line(plan: FestivalPlan) -> str:
    purpose = (plan.overview.purpose or "").strip()
    text = f"{purpose}에 함께해 주세요" if purpose else "많은 관심과 참여 부탁드려요"
    return shorten(text, LINE_MAX)


def poster_lines(plan: FestivalPlan) -> dict[str, str]:
    """포스터에 넣을 문구 6줄. 기획서 값으로만 코드가 정한다 (셔틀·주최·문의처·가격 등 없는 정보는 넣지 않는다).

    기간·장소는 사실 정보라 줄이지 않는다 (미확인은 "추후 공지").
    """
    texts = fixed_texts(plan)
    names = [p.name.strip() for p in plan.programs if p.name.strip()][:MAX_PROGRAMS]
    while names and len(" · ".join(names)) > LINE_MAX:
        names.pop()  # 이름 중간을 자르지 않고 뒤 프로그램을 뺀다
    lines = {
        "top": _concept_line(plan),
        "title": texts["title"],  # 줄이지 않는다 (render_poster가 글자 크기·줄바꿈으로 맞춘다)
        "period": texts["period"],
        "place": texts["place"],
        "box": " · ".join(names),
        "bottom": _closing_line(plan),
    }
    return {k: v for k, v in lines.items() if v}


# 지역 이름 → 영어 (국어의 로마자 표기법, 음운 변화는 반영하지 않은 단순 변환)
_INITIALS = [
    "g",
    "kk",
    "n",
    "d",
    "tt",
    "r",
    "m",
    "b",
    "pp",
    "s",
    "ss",
    "",
    "j",
    "jj",
    "ch",
    "k",
    "t",
    "p",
    "h",
]
_VOWELS = ["a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we",
           "wi", "yu", "eu", "ui", "i"]  # fmt: skip
_FINALS = ["", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l", "m", "p", "p",
           "t", "t", "ng", "t", "t", "k", "t", "p", "t"]  # fmt: skip


def romanize(word: str) -> str:
    out = []
    for i, ch in enumerate(word):
        if not ("가" <= ch <= "힣"):
            continue
        code = ord(ch) - 0xAC00
        cho, jung, jong = code // 588, (code % 588) // 28, code % 28
        initial = _INITIALS[cho]
        if (
            cho == 5 and out and out[-1].endswith(("l", "n"))
        ):  # ㄹ 앞이 ㄹ·ㄴ 받침이면 l (한림 → Hallim)
            out[-1] = out[-1][:-1] + "l"
            initial = "l"
        out.append(initial + _VOWELS[jung] + _FINALS[jong])
    return "".join(out).capitalize()


def region_en(region: str | None) -> str:
    """ "서귀포시 대정읍" → "Daejeong". 읍·면·동 글자는 뺀다."""
    if not region:
        return ""
    name = region.split()[-1]
    name = re.sub(r"[0-9]*(읍|면|동)$", "", name) or name
    return romanize(name)


TITLE_COLORS = {
    "자연": "green",
    "농산물": "orange",
    "수산물": "deep blue",
    "문화·생활": "brown",
    "경관": "purple",
}
SCENES = {
    "여름·물놀이": "a small summer water festival", "시장·상권": "a small local market",
    "정원·가드닝": "a small garden festival", "푸드·디저트": "a small food and dessert festival",
    "맥주·주류": "a small outdoor drinks festival", "도심·거리·골목": "a small alley street festival",
    "야간·빛·드론": "a small night light festival", "영화·책·아트": "a small art festival",
}  # fmt: skip


def text_poster_prompt(plan: FestivalPlan, lines: dict[str, str]) -> str:
    """한글 문구까지 그리는 포스터 그림 설명 (AI Studio에서 시험한 형식).

    장면은 재료·형식·계절·지역으로 만들고, 그 뒤에 위치별 문구를 따옴표로 넣는다.
    센터 데이터·집계 수치·예산은 넣지 않는다.
    """
    idea = plan.idea
    seasons = sorted(
        {SEASON_EN[m] for m in idea.timing.recommended_months}, key=list(SEASON_EN.values()).index
    )
    season = " and ".join(seasons)
    place = region_en(plan.overview.region)
    where = f"in {place}, Jeju Island" if place else "in Jeju Island"
    scene = SCENES.get(idea.format, "a small community festival")
    material = MATERIAL_EN.get(idea.material, "a local Jeju specialty")
    mood = FORMAT_MOOD.get(idea.format, "a cheerful community festival")
    color = TITLE_COLORS.get(idea.material_category, "orange")
    slots = [
        ("Top, small", lines.get("top")),
        (f"Title, large bold {color}", lines.get("title")),
        ("Under title, first line", lines.get("period")),
        ("Under title, second line", lines.get("place")),
        ("Bottom box", lines.get("box")),
        ("Bottom line", lines.get("bottom")),
    ]
    text_rules = "\n".join(f'- {where_}: "{text}"' for where_, text in slots if text)
    return (
        f"Vertical 3:4 festival poster, warm hand-drawn illustration of {scene} "
        f"{'in ' + season + ' ' if season else ''}{where}: {material}, {mood}, families walking. "
        "Leave clean space at the top and bottom for text.\n\n"
        "Render ONLY the following Korean text, exactly as written, with no other text anywhere "
        "(no signs on stalls, no English, no extra words, no numbers other than those given):\n"
        f"{text_rules}"
    )


def image_prompt(plan: FestivalPlan) -> str:
    """글자 없는 배경 그림 설명 (영어). 글자 넣은 포스터가 검사를 통과하지 못할 때 쓴다."""
    idea = plan.idea
    material = MATERIAL_EN.get(idea.material, "a local Jeju specialty")
    mood = FORMAT_MOOD.get(idea.format, "a cheerful community festival")
    seasons = sorted(
        {SEASON_EN[m] for m in idea.timing.recommended_months}, key=list(SEASON_EN.values()).index
    )
    season = " and ".join(seasons) or "pleasant"
    return (
        f"Vertical poster background illustration for a small local festival in Jeju Island, Korea. "
        f"Theme: {material}. Mood: {mood}. Season: {season}. "
        "Warm, friendly, family-oriented, clean composition with empty space in the lower third. "
        "No text, no letters, no numbers, no logos, no signs, no watermarks."
    )


# ---------- 이미지 받기 ----------


def _find_image_b64(data) -> str | None:
    """응답에서 base64 그림을 찾는다: output_image.data, 또는 steps/블록의 {"type": "image", "data"}."""
    if isinstance(data, dict):
        out = data.get("output_image")
        if isinstance(out, dict) and isinstance(out.get("data"), str):
            return out["data"]
        if data.get("type") == "image" and isinstance(data.get("data"), str):
            return data["data"]
        values = data.values()
    elif isinstance(data, list):
        values = data
    else:
        return None
    for v in values:
        if found := _find_image_b64(v):
            return found
    return None


def _raise_for(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    text = resp.text.lower()
    if resp.status_code == 429 or any(w in text for w in _QUOTA_WORDS):
        raise ImageQuotaError("이미지 모델 사용 한도나 결제 설정 문제예요.")
    if resp.status_code == 400 and ("aspect" in text or "ratio" in text):
        raise AspectRatioError("이미지 비율 설정을 받지 않았어요.")
    raise ImageGenerationError(f"이미지 생성 요청이 실패했어요 (HTTP {resp.status_code}).")


def request_image(
    prompt: str, api_key: str, model: str, client: httpx.Client, aspect_ratio: str | None
):
    fmt = {"type": "image", "image_size": IMAGE_SIZE}
    if aspect_ratio:
        fmt["aspect_ratio"] = aspect_ratio
    try:
        resp = client.post(
            ENDPOINT,
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
                "Api-Revision": API_REVISION,
            },
            json={"model": model, "input": prompt, "response_format": fmt},
        )
    except httpx.HTTPError as exc:
        raise ImageGenerationError(
            f"이미지 서버에 연결하지 못했어요 ({type(exc).__name__})."
        ) from exc
    _raise_for(resp)
    b64 = _find_image_b64(resp.json())
    if not b64:
        raise ImageGenerationError("응답에 그림이 없어요.")
    try:
        return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    except Exception as exc:  # 깨진 그림도 기본 포스터로 대신한다
        raise ImageGenerationError("받은 그림을 열지 못했어요.") from exc


def generate_background(
    prompt: str, api_key: str, model: str = DEFAULT_IMAGE_MODEL, transport=None, timeout: float = 60
) -> tuple[Image.Image, bool]:
    """(그림, 다시 잘랐는지). 3:4로 먼저 요청하고, 비율 때문에 거절되면 비율 없이 다시 요청한다."""
    with httpx.Client(timeout=timeout, transport=transport) as client:
        try:
            img = request_image(prompt, api_key, model, client, ASPECT_RATIO)
            retried = False
        except AspectRatioError:
            img = request_image(prompt, api_key, model, client, None)
            retried = True
    off_ratio = abs(img.width * 4 - img.height * 3) > max(img.width, img.height) * 0.01
    return img, retried or off_ratio


# ---------- 포스터 글자 읽기·검사 ----------

READ_SYSTEM = """포스터 그림에 보이는 글자를 그대로 옮겨 적는다. 고치거나 빼거나 보태지 않는다.
보이는 글자를 한 줄씩 적고, 글자가 없으면 빈 목록을 준다.
JSON으로만 답한다: {"lines": ["...", "..."]}"""


def read_poster_text(
    img: Image.Image, api_key: str, model: str, transport=None, timeout: float = 60
) -> list[str]:
    """텍스트 LLM(그림 입력)으로 포스터 글자를 읽는다. Interactions API의 image 입력 블록을 쓴다."""
    from agent.gemini import extract_text

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    body = {
        "model": model,
        "system_instruction": READ_SYSTEM,
        "input": [
            {"type": "text", "text": "이 포스터에 보이는 글자를 모두 그대로 적어줘."},
            {
                "type": "image",
                "mime_type": "image/png",
                "data": base64.b64encode(buf.getvalue()).decode(),
            },
        ],
        "response_format": {"type": "text", "mime_type": "application/json"},
    }
    try:
        with httpx.Client(timeout=timeout, transport=transport) as client:
            resp = client.post(
                ENDPOINT,
                headers={
                    "x-goog-api-key": api_key,
                    "Content-Type": "application/json",
                    "Api-Revision": API_REVISION,
                },
                json=body,
            )
        if resp.status_code >= 400:
            raise TextReadError(f"포스터 글자를 읽지 못했어요 (HTTP {resp.status_code}).")
        data = json.loads(_strip_fence(extract_text(resp.json())))
        return [str(x).strip() for x in data.get("lines", []) if str(x).strip()]
    except TextReadError:
        raise
    except Exception as exc:  # 네트워크·형식 오류 (키는 메시지에 넣지 않는다)
        raise TextReadError(f"포스터 글자를 읽지 못했어요 ({type(exc).__name__}).") from exc


def _norm(text: str) -> str:
    """비교용: 띄어쓰기·문장부호를 뺀다."""
    return re.sub(r"[\s·|•,.:;!?~'\"“”‘’()\[\]\-–—]+", "", text)


def check_poster_text(read_lines: list[str], lines: dict[str, str], allowed: set[str]) -> list[str]:
    """(a) 정한 문구가 다 있는지 (b) 정하지 않은 글자·기획서에 없는 숫자가 없는지. 문제 목록."""
    text = _norm(" ".join(read_lines)).replace(_norm(AI_CREDIT), "")
    problems = [f"빠진 문구: {v}" for v in lines.values() if _norm(v) not in text]
    rest = text
    for v in sorted(lines.values(), key=len, reverse=True):
        rest = rest.replace(_norm(v), "")
    extra = re.sub(r"[^0-9A-Za-z가-힣]", "", rest)
    if len(extra) > EXTRA_TOLERANCE:
        problems.append(f"정하지 않은 글자: {extra[:30]}")
    if nums := unknown_numbers(" ".join(read_lines).replace(AI_CREDIT, ""), allowed):
        problems.append(f"기획서에 없는 숫자: {', '.join(nums)}")
    return problems


# ---------- 포스터 그리기 ----------


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size)


def _cover(img: Image.Image, size=POSTER_SIZE) -> Image.Image:
    """비율을 지키며 채운 뒤 가운데를 잘라 size로 맞춘다."""
    w, h = size
    scale = max(w / img.width, h / img.height)
    resized = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (resized.width - w) // 2, (resized.height - h) // 2
    return resized.crop((left, top, left + w, top + h))


def _contain(img: Image.Image, size=POSTER_SIZE) -> Image.Image:
    """글자가 잘리지 않게 비율을 지켜 안에 넣고, 남는 곳은 가장자리 색으로 채운다."""
    w, h = size
    scale = min(w / img.width, h / img.height)
    resized = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    fill = resized.getpixel((0, 0))
    canvas = Image.new("RGB", size, fill)
    canvas.paste(resized, ((w - resized.width) // 2, (h - resized.height) // 2))
    return canvas


def add_credit(img: Image.Image) -> Image.Image:
    """AI 그림을 쓴 포스터 오른쪽 아래에 작게 AI 표기."""
    poster = img.convert("RGB").copy()
    draw = ImageDraw.Draw(poster)
    small = _font(24)
    w, h = poster.size
    tw = draw.textlength(AI_CREDIT, font=small)
    draw.text((w - 80 - tw + 2, h - 48), AI_CREDIT, font=small, fill=(40, 40, 40))  # 그림자
    draw.text((w - 80 - tw, h - 50), AI_CREDIT, font=small, fill=(235, 235, 235))
    return poster


def _wrap(draw, text: str, font, width: int) -> list[str]:
    """띄어쓰기에서 줄을 바꾼다. 한 낱말이 한 줄보다 길 때만 글자에서 끊는다."""
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}" if line else word
        if draw.textlength(trial, font=font) <= width:
            line = trial
            continue
        if line:
            lines.append(line)
        line = ""
        for ch in word:  # 낱말 하나가 너무 길면 글자에서 끊는다
            if draw.textlength(line + ch, font=font) > width and line:
                lines.append(line)
                line = ch
            else:
                line += ch
    return [*lines, line] if line else lines


def _title_lines(draw, title: str, width: int) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """제목이 두 줄 안에 들어가는 가장 큰 글자 크기. 가장 작은 크기로도 넘치면 세 줄까지."""
    for size in TITLE_FONT_SIZES:
        font = _font(size)
        lines = _wrap(draw, title, font, width)
        if len(lines) <= 2:
            return font, lines
    return font, lines[:3]


def render_poster(
    texts: dict[str, str], background: Image.Image | None, color=(46, 125, 90)
) -> Image.Image:
    """한글 문구를 얹은 1200×1600 포스터. background가 없으면 단색 기본 포스터 (AI 표기 없음)."""
    w, h = POSTER_SIZE
    base = _cover(background) if background is not None else Image.new("RGB", POSTER_SIZE, color)
    poster = base.convert("RGBA")
    band = Image.new("RGBA", POSTER_SIZE, (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    top = int(h * 0.62)
    bd.rectangle((0, top, w, h), fill=(0, 0, 0, 150 if background is not None else 60))
    poster = Image.alpha_composite(poster, band)
    draw = ImageDraw.Draw(poster)
    margin, y = 80, top + 60
    sub_font, small = _font(46), _font(24)
    title_font, title_lines = _title_lines(draw, texts["title"], w - margin * 2)
    for line in title_lines:
        draw.text((margin, y), line, font=title_font, fill="white")
        y += round(title_font.size * 1.28)
    y += 24
    for key in ("period", "place"):
        for line in _wrap(draw, texts[key], sub_font, w - margin * 2)[:2]:
            draw.text((margin, y), line, font=sub_font, fill=(255, 245, 225))
            y += 64
    del small
    if background is not None:  # AI 그림을 쓴 포스터만 표기
        return add_credit(poster)
    return poster.convert("RGB")


# ---------- SNS 글 ----------

SNS_SYSTEM = """당신은 제주 마을 축제의 인스타그램 홍보 글을 쓰는 사람이다.
입력 JSON의 값만 써서 한국어 글을 쓴다. 규칙:
1. 본문은 3~5문장, 친근한 말투.
2. "축제 이름" 값을 한 글자도 바꾸지 말고 그대로 한 번 넣는다.
3. 날짜·기간·장소 안내는 쓰지 않는다. "언제:", "어디:", "일시", "장소:" 같은 안내 줄도 만들지 않는다 (프로그램이 글 끝에 정확한 값을 붙인다).
4. 프로그램은 "프로그램" 목록에 있는 것만, 이름 위주로 짧게 소개한다. 컨셉 문장을 그대로 옮겨 붙이지 않는다. 목록에 없는 행사(드론 쇼, 불꽃놀이, 공연, 경품 등)를 지어내지 않는다.
5. 입력에 없는 숫자(날짜, 시간, 가격, 인원, 연도 등)를 쓰지 않는다.
6. 해시태그는 정확히 5개, 모두 #으로 시작하고 띄어쓰기와 숫자를 넣지 않는다. 목록에 없는 프로그램 이름도 넣지 않는다.
7. JSON으로만 답한다: {"text": "본문", "hashtags": ["#..", "#..", "#..", "#..", "#.."]}
"""


def _strip_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
    return raw.strip()


def unknown_numbers(text: str, allowed: set[str]) -> list[str]:
    """기획서 값에 없는 숫자 (월 표기는 허용). agent.plan의 숫자 검사와 같은 방식."""
    found = {m.group().replace(",", "") for m in _NUMBER.finditer(_MONTH.sub("", text))}
    return sorted(found - allowed, key=len)


# 본문에 AI가 직접 쓴 기간·장소 안내 줄 (코드가 붙이는 줄과 겹친다)
INFO_LABEL = re.compile(r"(언제|어디|일시|장소|기간)\s*(및\s*장소\s*)?[:：]|언제\s*·\s*어디")


# 컨셉 문장("…축제이다")을 붙여 생기는 비문: "축제이다랍니다", "제공한다를", "있다예요" 등
AWKWARD_ENDING = re.compile(
    r"[가-힣]*(?:이다|한다|된다|있다|없다|했다)(?:랍니다|답니다|를|을|예요|에요|이에요|요)"
)


def sns_problems(
    text: str, hashtags: list[str], plan: FestivalPlan, allowed: set[str]
) -> list[str]:
    """SNS 본문(언제·어디 줄을 붙이기 전) 검사. 문제 목록."""
    problems = []
    title = plan.overview.name
    if title not in text:
        problems.append(f"축제 이름 '{title}'이(가) 그대로 들어가지 않았어요")
    if len(hashtags) != HASHTAG_COUNT or not all(t.startswith("#") for t in hashtags):
        problems.append(f"해시태그가 #으로 시작하는 {HASHTAG_COUNT}개가 아니에요")
    if extra := unknown_numbers(text + " " + " ".join(hashtags), allowed):
        problems.append(f"기획서에 없는 숫자가 있어요: {', '.join(extra)}")
    if bad := AWKWARD_ENDING.search(text):
        problems.append(f"어색한 문장이 있어요: '{bad.group()}' (문장을 자연스럽게 고쳐 쓰세요)")
    if spaced := [t for t in hashtags if re.search(r"\s", t)]:
        problems.append(f"해시태그에 띄어쓰기가 있어요: {', '.join(spaced)}")
    if INFO_LABEL.search(text):
        problems.append("언제·어디 안내 줄은 쓰지 마세요 (따로 붙여요)")
    if extra := unplanned_programs(text + " " + " ".join(hashtags), plan):
        problems.append(f"기획서 프로그램에 없는 내용이 있어요: {', '.join(extra)}")
    return problems


def write_sns(plan: FestivalPlan, llm) -> tuple[str | None, list[str], str | None]:
    """(본문, 해시태그, 안내). 문제가 있으면 다시 생성하고, 끝까지 안 되면 마지막 글과 경고."""
    from agent.plan import allowed_numbers

    payload = promo_payload(plan)
    info = sns_info(plan)
    allowed = allowed_numbers(payload)
    user = "<input>\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n</input>"
    problem, last = "", (None, [])
    for _ in range(SNS_ATTEMPTS):
        prompt = user + (
            f"\n\n이전 응답의 문제: {problem}\n규칙을 지켜 다시 쓰세요." if problem else ""
        )
        try:
            raw = llm.complete_json(SNS_SYSTEM, prompt)
            data = json.loads(_strip_fence(raw))
            text = str(data.get("text", "")).strip()
            tags = [str(t).strip() for t in data.get("hashtags", [])]
        except Exception as exc:  # noqa: BLE001 - LLM 오류·형식 오류는 다시 시도
            problem = "JSON 형식이 맞지 않았어요" if isinstance(exc, ValueError) else str(exc)
            continue
        last = (f"{text}\n\n{info['line']}", tags)  # 언제·어디는 코드가 붙인다
        problems = sns_problems(text, tags, plan, allowed)
        if not problems:
            return last[0], tags, None
        problem = "; ".join(problems)
    if last[0] is None:
        return None, [], f"SNS 글을 만들지 못했어요. {problem}"
    return (
        last[0],
        last[1],
        f"{SNS_ATTEMPTS}번 써 봐도 검사를 통과하지 못했어요. 확인 필요: {problem}",
    )


# ---------- 정보 일치 검사 ----------


def consistency_checks(plan: FestivalPlan, result: "PromoResult") -> list[PromoCheck]:
    from agent.plan import allowed_numbers

    texts = fixed_texts(plan)
    allowed = allowed_numbers(promo_payload(plan))
    checks = []
    for key, label in (("title", "축제 이름"), ("period", "기간"), ("place", "장소")):
        shown = result.poster_text.get(key, "")
        same = shown == texts[key] or (key == "title" and shown and texts[key].startswith(shown))
        detail = (
            texts[key] if shown == texts[key] else f"{shown} (기획서: {texts[key]}, 길어서 줄임)"
        )
        checks.append(PromoCheck(item=f"포스터 {label}", ok=bool(same), detail=detail))
    if result.poster_mode == "ai_text":
        checks.append(PromoCheck(item="포스터 글자 검사", ok=not result.text_problems,
                                 detail="정한 문구만 그대로 들어갔어요"))  # fmt: skip
    extra = unplanned_programs(" ".join(result.poster_lines.values()), plan)
    checks.append(PromoCheck(item="포스터 프로그램 (기획서에 있는 것만)", ok=not extra,
                             detail=", ".join(extra) or "기획서 프로그램만 썼어요"))  # fmt: skip
    if result.sns_text is None:
        checks.append(PromoCheck(item="SNS 글", ok=False, detail="만들지 못했어요"))
        return checks
    info = sns_info(plan)
    for label, value in (
        ("축제 이름", texts["title"]),
        ("기간", info["when"]),
        ("장소", info["where"]),
    ):
        checks.append(PromoCheck(item=f"SNS {label}", ok=value in result.sns_text, detail=value))
    sns_all = result.sns_text + " " + " ".join(result.hashtags)
    extra = unplanned_programs(sns_all, plan)
    checks.append(PromoCheck(item="SNS 프로그램 (기획서에 있는 것만)", ok=not extra,
                             detail=", ".join(extra) or "기획서 프로그램만 썼어요"))  # fmt: skip
    extra = unknown_numbers(sns_all, allowed)
    checks.append(
        PromoCheck(item="기획서에 없는 숫자", ok=not extra, detail=", ".join(extra) or "없음")
    )
    checks.append(
        PromoCheck(
            item="해시태그 5개",
            ok=len(result.hashtags) == HASHTAG_COUNT,
            detail=" ".join(result.hashtags),
        )
    )
    return checks


# ---------- 한 번에 만들기 ----------


def make_promo(
    plan: FestivalPlan,
    *,
    api_key: str | None = None,
    image_model: str | None = None,
    llm=None,
    transport=None,
    out_dir: Path | None = None,
    text_model: str | None = None,
) -> PromoResult:
    """승인된 기획서로 포스터와 SNS 글을 만든다. 승인 전이면 agent.plan.PlanNotApprovedError."""
    from agent.plan import require_approved

    require_approved(plan)
    from agent.gemini import DEFAULT_MODEL as DEFAULT_TEXT_MODEL
    from agent.plan import allowed_numbers

    texts = fixed_texts(plan)
    lines = poster_lines(plan)
    prompt = text_poster_prompt(plan, lines)
    allowed = allowed_numbers({**promo_payload(plan), **lines})
    color = CATEGORY_COLORS.get(plan.idea.material_category, (46, 125, 90))
    model = image_model or DEFAULT_IMAGE_MODEL
    mode, poster, cropped, notice, attempts, problems = "plain", None, False, None, 0, []
    if not api_key:
        notice = NO_KEY_NOTICE
    else:
        try:
            # 1) 이미지 모델이 한글 문구까지 그린다. 글자를 읽어 검사하고, 틀리면 다시 (최대 2번)
            for _ in range(POSTER_ATTEMPTS):
                attempts += 1
                img, cropped = generate_background(prompt, api_key, model, transport=transport)
                try:
                    read = read_poster_text(
                        img, api_key, text_model or DEFAULT_TEXT_MODEL, transport
                    )
                except TextReadError as exc:
                    problems = [str(exc)]
                    break  # 검사를 못 하면 글자를 따로 얹는다
                problems = check_poster_text(read, lines, allowed)
                if not problems:
                    mode, poster = "ai_text", add_credit(_contain(img))
                    break
            # 2) 그래도 틀리면 지금 방식: 글자 없는 그림 + Pillow 한글
            if mode != "ai_text":
                background, cropped = generate_background(
                    image_prompt(plan), api_key, model, transport=transport
                )
                mode, notice = "overlay", TEXT_FALLBACK_NOTICE
                poster = render_poster({**texts, "title": lines["title"]}, background, color)
        except ImageQuotaError:
            mode, notice = "plain", QUOTA_NOTICE
        except ImageGenerationError:
            mode, notice = "plain", FAIL_NOTICE
    if poster is None or mode == "plain":
        mode, poster = "plain", render_poster({**texts, "title": lines["title"]}, None, color)
    out_dir = OUTPUT_DIR if out_dir is None else out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{plan.plan_id}_v{plan.version}_poster.png"
    poster.save(path, format="PNG")

    if llm is None:
        sns_text, tags, sns_notice = None, [], "AI 설정이 없어 SNS 글을 만들지 못했어요."
    else:
        sns_text, tags, sns_notice = write_sns(plan, llm)
    result = PromoResult(
        plan_id=plan.plan_id,
        plan_version=plan.version,
        created_at=datetime.now(UTC),
        poster_path=str(path),
        poster_text={**texts, "title": lines["title"]},
        poster_lines=lines,
        poster_mode=mode,
        text_attempts=attempts,
        text_problems=problems if mode != "ai_text" else [],
        used_ai_image=mode in ("ai_text", "overlay"),
        image_cropped=cropped,
        image_prompt=prompt,
        image_notice=notice,
        sns_text=sns_text,
        hashtags=tags,
        sns_notice=sns_notice,
        is_synthetic=plan.is_synthetic,
    )
    result.checks = consistency_checks(plan, result)
    return result


# ---------- 저장 (outputs/, Git 제외) ----------


def sns_copy_text(result: PromoResult) -> str:
    """복사·저장용 SNS 글: 본문 + 빈 줄 + 해시태그. SNS 글이 없으면 빈 문자열."""
    if not result.sns_text:
        return ""
    tags = " ".join(result.hashtags)
    return result.sns_text + (f"\n\n{tags}" if tags else "")


def promo_stem(result: PromoResult) -> str:
    """포스터·SNS 문구·ZIP 파일 이름 앞부분. 같은 기획서 버전끼리 묶인다."""
    return f"{result.plan_id}_v{result.plan_version}"


def save_promo_files(result: PromoResult, out_dir: Path | None = None) -> list[Path]:
    """포스터(이미 저장됨)와 SNS 문구를 같은 기획서 버전 이름으로 저장한다. 저장한 파일 목록."""
    out_dir = OUTPUT_DIR if out_dir is None else out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = [Path(result.poster_path)]
    if text := sns_copy_text(result):
        sns = out_dir / f"{promo_stem(result)}_sns.txt"
        sns.write_text(text + "\n", encoding="utf-8")
        saved.append(sns)
    return saved


def promo_zip_bytes(result: PromoResult, plan_markdown: str) -> bytes:
    """poster.png · sns.txt · plan.md를 묶은 ZIP. SNS 글이 없으면 sns.txt는 뺀다."""
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(result.poster_path, "poster.png")
        if text := sns_copy_text(result):
            zf.writestr("sns.txt", text + "\n")
        zf.writestr("plan.md", plan_markdown)
    return buf.getvalue()


def save_promo_zip(result: PromoResult, data: bytes, out_dir: Path | None = None) -> Path:
    out_dir = OUTPUT_DIR if out_dir is None else out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{promo_stem(result)}_promo.zip"
    path.write_bytes(data)
    return path
