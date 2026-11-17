import base64
import io
import json
import re
from datetime import UTC, datetime

import httpx
import pytest
from PIL import Image

from agent.demo_cards import DEMO_REQUEST, demo_proposal
from agent.fake_checks import FAKE_TOOLS
from agent.plan import PlanNotApprovedError, approve_plan, generate_plan
from agent.verify import verify_idea
from app import promo

NOW = datetime(2026, 11, 17, 9, 0, tzinfo=UTC)
PLAN_TEXT = {
    "background": "애월 상권에 손님을 모으는 작은 마켓을 제안한다.",
    "concept": "수확철 감귤과 지역 가게가 함께 여는 주말 마켓이다.",
    "programs": [
        {"name": "감귤 직거래 장터", "description": "농가가 직접 파는 장터"},
        {"name": "감귤 디저트 부스", "description": "지역 카페가 참여하는 시식 부스"},
    ],
    "promotion": "마을 게시판과 SNS를 함께 쓴다.",
    "operation": "장소와 인력은 미확인이다.",
    "risk": "같은 재료 축제와 날짜를 겹치지 않게 잡는다.",
    "expected": "지역 가게에 손님이 늘 것으로 보인다.",
    "assumptions": ["참여할 감귤 농가를 모을 수 있다"],
}


class FakeLLM:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def complete_json(self, system, user):
        self.calls.append(user)
        r = self.responses.pop(0)
        return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)


@pytest.fixture(scope="module")
def draft():
    run = verify_idea(
        demo_proposal().ideas[0], DEMO_REQUEST, FAKE_TOOLS, festivals_by_month={12: 1}
    )
    return generate_plan(run, DEMO_REQUEST, FakeLLM(PLAN_TEXT), approved=True, now=NOW)


@pytest.fixture(scope="module")
def plan(draft):
    return approve_plan(draft, now=NOW)


def png_b64(size) -> str:
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 120, 40)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def good_sns(plan, **override):
    t = promo.fixed_texts(plan)
    data = {
        "text": f"{t['title']}에 놀러 오세요! 기간은 {t['period']}이에요. 장소는 {t['place']}예요. "
        "감귤과 지역 가게가 함께하는 주말 마켓이에요.",
        "hashtags": ["#제주축제", "#애월", "#감귤", "#로컬마켓", "#가족나들이"],
    }
    return data | override


def test_promo_blocked_before_approval(draft, tmp_path):
    assert draft.status == "draft"
    with pytest.raises(PlanNotApprovedError, match="최종 승인한 뒤에"):
        promo.make_promo(draft, out_dir=tmp_path)


def test_unconfirmed_fields_are_not_made_up(plan):
    texts = promo.fixed_texts(plan)
    assert texts["title"] == plan.overview.name
    assert plan.idea.timing.recommended_months == [11]  # 가짜 확인 도구가 12월 → 11월로 고침
    assert texts["period"] == "11월 중 · 날짜 추후 공지"  # "11월 중 (날짜 미확인)"
    assert texts["place"] == "제주시 애월읍 · 장소 추후 공지"  # 장소 미확인
    gone = plan.model_copy(
        update={"overview": plan.overview.model_copy(update={"period": "미확인", "region": None})}
    )
    assert promo.fixed_texts(gone)["period"] == "일정 추후 공지"
    assert promo.fixed_texts(gone)["place"] == "장소 추후 공지"


def test_fallback_prompt_has_no_text_numbers_or_korean(plan):
    prompt = promo.image_prompt(plan)  # 글자 검사를 통과하지 못할 때 쓰는 글자 없는 그림
    assert "No text, no letters" in prompt
    assert "tangerine" in prompt and "autumn" in prompt  # 11월
    assert not re.search(r"\d", prompt) and not re.search(r"[가-힣]", prompt)
    assert plan.overview.name not in prompt


class FakeGemini:
    """이미지 요청(response_format.type == image)과 글자 읽기 요청을 나눠 순서대로 응답한다."""

    def __init__(self, images=(), reads=()):
        self.images, self.reads = list(images), list(reads)
        self.image_requests, self.read_requests = [], []

    def __call__(self, request: httpx.Request):
        body = json.loads(request.content)
        if body.get("response_format", {}).get("type") == "image":
            self.image_requests.append(body)
            status, data = self.images.pop(0)
        else:
            self.read_requests.append(body)
            status, data = self.reads.pop(0)
        if isinstance(data, str):
            return httpx.Response(status, text=data)
        return httpx.Response(status, json=data)

    @property
    def transport(self):
        return httpx.MockTransport(self)


def image_ok(size=(900, 1200)):
    return (200, {"output_image": {"data": png_b64(size)}})


def read_ok(lines):
    """글자 읽기 응답 (Interactions text 응답 모양)."""
    text = json.dumps({"lines": lines}, ensure_ascii=False)
    return (
        200,
        {
            "status": "completed",
            "steps": [{"type": "model_output", "content": [{"type": "text", "text": text}]}],
        },
    )


def exact_read(plan):
    return read_ok([*promo.poster_lines(plan).values(), promo.AI_CREDIT])


def test_poster_with_korean_text_passes_check(plan, tmp_path):
    fake = FakeGemini([image_ok()], [exact_read(plan)])
    result = promo.make_promo(plan, api_key="test-key", llm=FakeLLM(good_sns(plan)),
                              out_dir=tmp_path, transport=fake.transport)  # fmt: skip
    assert (
        result.poster_mode == "ai_text"
        and result.text_attempts == 1
        and result.image_notice is None
    )
    img = Image.open(result.poster_path)
    assert img.size == (1200, 1600) and img.format == "PNG"
    body = fake.image_requests[0]
    assert body["model"] == promo.DEFAULT_IMAGE_MODEL
    assert body["response_format"] == {"type": "image", "image_size": "1K", "aspect_ratio": "3:4"}
    assert (
        body["input"] == result.image_prompt
        and "Render ONLY the following Korean text" in body["input"]
    )
    read = fake.read_requests[0]
    assert read["input"][1]["type"] == "image" and read["input"][1]["mime_type"] == "image/png"
    assert all(c.ok for c in result.checks), result.checks
    assert any(c.item == "포스터 글자 검사" and c.ok for c in result.checks)


def test_wrong_text_is_regenerated_then_passes(plan, tmp_path):
    lines = list(promo.poster_lines(plan).values())
    shuttle = read_ok([*lines, "셔틀버스 운행"])  # 정하지 않은 글자
    fake = FakeGemini([image_ok(), image_ok()], [shuttle, exact_read(plan)])
    result = promo.make_promo(plan, api_key="k", out_dir=tmp_path, transport=fake.transport)
    assert result.poster_mode == "ai_text" and result.text_attempts == 2


def test_text_check_keeps_failing_then_overlay(plan, tmp_path):
    lines = list(promo.poster_lines(plan).values())
    missing = read_ok(lines[1:])  # 맨 위 문구 빠짐
    number = read_ok([*lines, "입장료 5000원"])  # 기획서에 없는 숫자
    fake = FakeGemini([image_ok()] * 4, [missing, number, missing])
    result = promo.make_promo(plan, api_key="k", out_dir=tmp_path, transport=fake.transport)
    assert result.text_attempts == promo.POSTER_ATTEMPTS == 3
    assert result.poster_mode == "overlay" and result.used_ai_image
    assert result.image_notice == promo.TEXT_FALLBACK_NOTICE
    assert "글자를 따로 얹었어요" in result.image_notice
    assert any("빠진 문구" in p for p in result.text_problems)
    assert "No text, no letters" in fake.image_requests[3]["input"]  # 4번째는 글자 없는 그림
    assert Image.open(result.poster_path).size == (1200, 1600)


def test_unreadable_poster_goes_to_overlay(plan, tmp_path):
    fake = FakeGemini([image_ok(), image_ok()], [(500, "server error")])
    result = promo.make_promo(plan, api_key="k", out_dir=tmp_path, transport=fake.transport)
    assert result.poster_mode == "overlay" and result.text_attempts == 1
    assert "읽지 못했어요" in result.text_problems[0]


def test_check_poster_text_rules(plan):
    lines = promo.poster_lines(plan)
    allowed = {"11"}
    assert (
        promo.check_poster_text([*lines.values(), promo.AI_CREDIT], lines, allowed) == []
    )  # AI 표기는 뺌
    spaced = [v.replace(" ", "") for v in lines.values()]  # 띄어쓰기 차이는 봐줌
    assert promo.check_poster_text(spaced, lines, allowed) == []
    problems = promo.check_poster_text([*lines.values(), "문의 064"], lines, allowed)
    assert any("정하지 않은 글자" in p for p in problems) and any("064" in p for p in problems)
    assert any(
        "빠진 문구" in p for p in promo.check_poster_text(list(lines.values())[:-1], lines, allowed)
    )


def test_steps_shaped_response_is_read(plan, tmp_path):
    steps = {"steps": [{"type": "model_output", "content": [{"type": "text", "text": "ok"},
                                                            {"type": "image", "data": png_b64((300, 400))}]}]}  # fmt: skip
    fake = FakeGemini([(200, steps)], [exact_read(plan)])
    result = promo.make_promo(plan, api_key="k", out_dir=tmp_path, transport=fake.transport)
    assert result.poster_mode == "ai_text"


def test_ai_credit_only_on_ai_poster():
    texts = {
        "title": "감귤 마켓",
        "period": "12월 중 · 날짜 추후 공지",
        "place": "제주시 애월읍 · 장소 추후 공지",
    }
    gray = Image.new("RGB", (1200, 1600), (128, 128, 128))
    ai = promo.render_poster(texts, gray)
    plain = promo.render_poster(texts, None, (128, 128, 128))
    box = (800, 1535, 1130, 1580)  # 오른쪽 아래 작은 글씨 자리
    assert ai.crop(box).convert("L").getextrema()[0] != ai.crop(box).convert("L").getextrema()[1]
    lo, hi = plain.crop(box).convert("L").getextrema()
    assert lo == hi  # 단색 기본 포스터에는 AI 표기 없음
    assert promo.AI_CREDIT == "이미지: AI 생성 (Gemini)"
    text_poster = promo.add_credit(gray)  # 글자까지 그린 포스터에도 표기
    lo, hi = text_poster.crop(box).convert("L").getextrema()
    assert lo != hi


def test_aspect_ratio_rejected_then_retried(plan, tmp_path):
    fake = FakeGemini(
        [(400, {"error": {"message": "aspect_ratio 3:4 is not supported for this model"}}), image_ok((1600, 900))],
        [exact_read(plan)],
    )  # fmt: skip
    result = promo.make_promo(plan, api_key="k", out_dir=tmp_path, transport=fake.transport)
    assert "aspect_ratio" in fake.image_requests[0]["response_format"]
    assert "aspect_ratio" not in fake.image_requests[1]["response_format"]
    assert result.poster_mode == "ai_text" and result.image_cropped
    assert Image.open(result.poster_path).size == (1200, 1600)  # 글자가 잘리지 않게 안에 넣어 맞춤


def test_other_ratio_is_fitted(plan, tmp_path):
    fake = FakeGemini([image_ok((1024, 1024))], [exact_read(plan)])
    result = promo.make_promo(plan, api_key="k", out_dir=tmp_path, transport=fake.transport)
    assert result.image_cropped and Image.open(result.poster_path).size == (1200, 1600)


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded, limit: 0"}}),
        (403, "Image generation requires billing to be enabled"),
    ],
)
def test_quota_error_makes_plain_poster_with_notice(plan, tmp_path, status, body):
    fake = FakeGemini([(status, body)])
    result = promo.make_promo(plan, api_key="k", out_dir=tmp_path, transport=fake.transport)
    assert result.poster_mode == "plain" and not result.used_ai_image
    assert result.image_notice == promo.QUOTA_NOTICE
    assert "AI Studio" in result.image_notice and "Render ONLY" in result.image_prompt
    assert Image.open(result.poster_path).size == (1200, 1600)  # 기본 포스터는 만든다


# ---------- 포스터 문구 ----------


def test_poster_lines_use_only_plan_info(plan):
    lines = promo.poster_lines(plan)
    assert lines["title"] == plan.overview.name
    assert (
        lines["period"] == "11월 중 · 날짜 추후 공지"
        and lines["place"] == "제주시 애월읍 · 장소 추후 공지"
    )
    assert lines["box"] == "감귤 직거래 장터 · 감귤 디저트 부스"  # 기획서 programs 이름만
    assert lines["top"] == "수확철 감귤과 지역 가게가 함께 여는 주말 마켓"  # 컨셉 첫 문장
    assert lines["bottom"] == "지역 상권 활성화에 함께해 주세요"  # 목적
    shown = " ".join(lines.values())
    for word in ("셔틀", "주최", "문의", "가격", "입장료", "무료", "원)", "만 원"):
        assert word not in shown, word  # 기획서 운영 문단(셔틀 등)이나 예산은 넣지 않음


def test_prompt_has_only_fixed_lines(plan):
    lines = promo.poster_lines(plan)
    prompt = promo.text_poster_prompt(plan, lines)
    quoted = re.findall(r'"([^"]+)"', prompt)
    assert quoted == list(lines.values())  # 따옴표 안에는 정한 문구만
    assert "Render ONLY the following Korean text, exactly as written" in prompt
    assert "no text, no letters" not in prompt.lower()
    outside = re.sub(r'"[^"]*"', "", prompt)
    assert not re.search(r"[가-힣]", outside)  # 한글은 따옴표 안에만
    assert not re.search(r"\d", outside.replace("3:4", ""))  # 숫자·예산·집계 수치 없음
    assert "Aewol" in prompt and "autumn" in prompt


def test_long_texts_are_shortened(plan):
    long = plan.model_copy(update={
        "overview": plan.overview.model_copy(update={"name": "제주 애월 감귤과 바다가 함께하는 겨울 로컬 마켓 대축제"}),
        "programs": [p.model_copy(update={"name": n}) for p, n in zip(
            [plan.programs[0]] * 4, ["감귤 직거래 장터", "감귤 디저트 만들기 체험 부스", "골목 먹거리", "음악 공연"])],
    })  # fmt: skip
    lines = promo.poster_lines(long)
    assert len(lines["title"]) <= promo.TITLE_MAX and long.overview.name.startswith(lines["title"])
    assert all(len(v) <= promo.LINE_MAX for k, v in lines.items() if k not in ("period", "place"))
    assert all(name in ["감귤 직거래 장터", "감귤 디저트 만들기 체험 부스", "골목 먹거리"]
               for name in lines["box"].split(" · "))  # 이름 중간을 자르지 않고 뒤에서 뺌  # fmt: skip
    assert promo.shorten("가나다 라마바 사아자", 7) == "가나다"
    assert promo.shorten("가나다라마바사아자", 5) == "가나다라마"


def test_sns_with_unknown_number_is_regenerated(plan, tmp_path):
    bad = good_sns(plan, text=good_sns(plan)["text"] + " 입장료 5000원, 2027년에도 열려요.")
    llm = FakeLLM(bad, good_sns(plan))
    result = promo.make_promo(plan, llm=llm, out_dir=tmp_path)
    assert len(llm.calls) == 2 and "기획서에 없는 숫자" in llm.calls[1]
    assert "5000" not in result.sns_text and result.sns_notice is None
    # 계속 숫자가 나오면 마지막 글을 경고와 함께 보여준다
    llm = FakeLLM(bad, bad, bad)
    result = promo.make_promo(plan, llm=llm, out_dir=tmp_path)
    assert len(llm.calls) == promo.SNS_ATTEMPTS
    assert "확인 필요" in result.sns_notice and "2027" in result.sns_notice
    number_check = next(c for c in result.checks if c.item == "기획서에 없는 숫자")
    assert not number_check.ok and "5000" in number_check.detail


def test_month_numbers_are_allowed(plan):
    allowed = {"16"}
    assert promo.unknown_numbers("12월 중 · 날짜 추후 공지, 16개", allowed) == []
    assert promo.unknown_numbers("12월 3일", allowed) == ["3"]


def test_sns_missing_fixed_text_is_regenerated(plan, tmp_path):
    wrong = good_sns(plan, text="12월 25일 애월에서 만나요! 즐거운 축제예요. 많이 와 주세요.")
    llm = FakeLLM(wrong, good_sns(plan))
    result = promo.make_promo(plan, llm=llm, out_dir=tmp_path)
    assert len(llm.calls) == 2 and result.sns_notice is None
    assert all(c.ok for c in result.checks)


def test_no_key_still_makes_plain_poster(plan, tmp_path):
    result = promo.make_promo(plan, out_dir=tmp_path)
    assert not result.used_ai_image and result.image_notice == promo.NO_KEY_NOTICE
    assert result.sns_text is None and "SNS 글을 만들지 못했어요" in result.sns_notice
    assert result.is_synthetic == plan.is_synthetic
