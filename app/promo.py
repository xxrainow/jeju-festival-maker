"""홍보물 (포스터 + SNS 글). 승인된 기획서(FestivalPlan)로만 만든다 (CLAUDE.md 2절 9단계).

- 기획서에서 축제 이름, 기간, 지역, 장소, 대상, 재료, 형식, 컨셉만 쓴다. 센터 데이터·집계 수치는 쓰지 않는다
- 미확인 칸은 지어내지 않고 "날짜 추후 공지", "장소 추후 공지"로 쓴다 (fixed_texts)
- 포스터: Gemini 이미지 모델로 글자 없는 배경 그림을 받고(그림 설명은 영어, 이름·기간·장소·숫자 없음),
  Pillow로 한글 문구를 얹어 1200×1600(3:4) PNG로 저장한다. 그림을 못 받으면 단색 기본 포스터
- SNS 글: A의 LLM 연결(agent.proposals.default_llm)로 인스타그램 글 3~5문장 + 해시태그 5개
- 정보 일치 검사: 고정 문구(이름·기간·장소)가 그대로 들어갔는지, 기획서에 없는 숫자가 없는지
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
AI_CREDIT = "배경 이미지: AI 생성 (Gemini)"
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
    poster_text: dict[str, str]  # title, period, place
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


def promo_payload(plan: FestivalPlan) -> dict:
    """SNS 글에 넘기는 기획서 값. 숫자 허용 목록도 여기서 만든다."""
    texts = fixed_texts(plan)
    return {
        "축제 이름": texts["title"],
        "기간": texts["period"],
        "장소": texts["place"],
        "대상": plan.overview.target or "",
        "재료": plan.idea.material,
        "형식": plan.idea.format,
        "컨셉": _section(plan, "concept") or plan.idea.concept,
    }


def image_prompt(plan: FestivalPlan) -> str:
    """배경 그림 설명 (영어). 이름·기간·장소·숫자·센터 데이터는 넣지 않는다."""
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


def _wrap(draw, text: str, font, width: int) -> list[str]:
    lines, line = [], ""
    for ch in text:
        if draw.textlength(line + ch, font=font) > width and line:
            lines.append(line)
            line = ch
        else:
            line += ch
    return [*lines, line] if line else lines


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
    title_font, sub_font, small = _font(84), _font(46), _font(24)
    for line in _wrap(draw, texts["title"], title_font, w - margin * 2)[:3]:
        draw.text((margin, y), line, font=title_font, fill="white")
        y += 108
    y += 24
    for key in ("period", "place"):
        for line in _wrap(draw, texts[key], sub_font, w - margin * 2)[:2]:
            draw.text((margin, y), line, font=sub_font, fill=(255, 245, 225))
            y += 64
    if background is not None:  # AI 그림을 쓴 포스터만 표기
        tw = draw.textlength(AI_CREDIT, font=small)
        draw.text((w - margin - tw, h - 50), AI_CREDIT, font=small, fill=(230, 230, 230))
    return poster.convert("RGB")


# ---------- SNS 글 ----------

SNS_SYSTEM = """당신은 제주 마을 축제의 인스타그램 홍보 글을 쓰는 사람이다.
입력 JSON의 값만 써서 한국어 글을 쓴다. 규칙:
1. 본문은 3~5문장, 친근한 말투.
2. "축제 이름", "기간", "장소" 값을 한 글자도 바꾸지 말고 그대로 넣는다.
3. 입력에 없는 숫자(날짜, 시간, 가격, 인원, 연도 등)를 쓰지 않는다. 정해지지 않은 것은 "추후 공지"라고 쓴다.
4. 해시태그는 정확히 5개, 모두 #으로 시작하고 숫자를 넣지 않는다.
5. JSON으로만 답한다: {"text": "본문", "hashtags": ["#..", "#..", "#..", "#..", "#.."]}
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


def sns_problems(
    text: str, hashtags: list[str], texts: dict[str, str], allowed: set[str]
) -> list[str]:
    problems = []
    for key, label in (("title", "축제 이름"), ("period", "기간"), ("place", "장소")):
        if texts[key] not in text:
            problems.append(f"{label} '{texts[key]}'이(가) 그대로 들어가지 않았어요")
    if len(hashtags) != HASHTAG_COUNT or not all(t.startswith("#") for t in hashtags):
        problems.append(f"해시태그가 #으로 시작하는 {HASHTAG_COUNT}개가 아니에요")
    if extra := unknown_numbers(text + " " + " ".join(hashtags), allowed):
        problems.append(f"기획서에 없는 숫자가 있어요: {', '.join(extra)}")
    return problems


def write_sns(plan: FestivalPlan, llm) -> tuple[str | None, list[str], str | None]:
    """(본문, 해시태그, 안내). 문제가 있으면 다시 생성하고, 끝까지 안 되면 마지막 글과 경고."""
    from agent.plan import allowed_numbers

    payload = promo_payload(plan)
    texts = fixed_texts(plan)
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
        last = (text, tags)
        problems = sns_problems(text, tags, texts, allowed)
        if not problems:
            return text, tags, None
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
        same = result.poster_text.get(key) == texts[key]
        checks.append(PromoCheck(item=f"포스터 {label}", ok=same, detail=texts[key]))
    if result.sns_text is None:
        checks.append(PromoCheck(item="SNS 글", ok=False, detail="만들지 못했어요"))
        return checks
    for key, label in (("title", "축제 이름"), ("period", "기간"), ("place", "장소")):
        checks.append(
            PromoCheck(item=f"SNS {label}", ok=texts[key] in result.sns_text, detail=texts[key])
        )
    extra = unknown_numbers(result.sns_text + " " + " ".join(result.hashtags), allowed)
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
) -> PromoResult:
    """승인된 기획서로 포스터와 SNS 글을 만든다. 승인 전이면 agent.plan.PlanNotApprovedError."""
    from agent.plan import require_approved

    require_approved(plan)
    texts = fixed_texts(plan)
    prompt = image_prompt(plan)
    background, cropped, notice = None, False, None
    if not api_key:
        notice = NO_KEY_NOTICE
    else:
        try:
            background, cropped = generate_background(
                prompt, api_key, image_model or DEFAULT_IMAGE_MODEL, transport=transport
            )
        except ImageQuotaError:
            notice = QUOTA_NOTICE
        except ImageGenerationError:
            notice = FAIL_NOTICE
    color = CATEGORY_COLORS.get(plan.idea.material_category, (46, 125, 90))
    poster = render_poster(texts, background, color)
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
        poster_text=texts,
        used_ai_image=background is not None,
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
