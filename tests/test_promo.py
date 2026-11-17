import base64
import io
import json
import re
from datetime import UTC, datetime

import httpx
import pytest
from PIL import Image

from agent.demo_cards import DEMO_REQUEST
from agent.fake_checks import FAKE_TOOLS
from agent.plan import PlanNotApprovedError, approve_plan, generate_plan
from agent.verify import verify_idea
from app import promo
from tests.demo_helpers import december_demo  # noqa: F401 - 픽스처
from tests.demo_helpers import december_demo_proposal as demo_proposal

# 데모 카드 1은 시연용으로 1월이지만, 이 파일은 원래 12월 카드(→ 11월로 수정) 기준이다
pytestmark = pytest.mark.usefixtures("december_demo")

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


def transport(*responses, seen=None):
    """요청을 순서대로 받아 응답한다. responses: (상태, JSON 또는 글자)."""
    queue = list(responses)

    def handle(request: httpx.Request):
        if seen is not None:
            seen.append(request)
        status, body = queue.pop(0)
        if isinstance(body, str):
            return httpx.Response(status, text=body)
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handle)


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


def test_image_prompt_has_no_text_numbers_or_korean(plan):
    prompt = promo.image_prompt(plan)
    assert "No text, no letters" in prompt
    assert "tangerine" in prompt and "autumn" in prompt  # 11월
    assert not re.search(r"\d", prompt) and not re.search(r"[가-힣]", prompt)
    assert plan.overview.name not in prompt


def test_fake_image_makes_ai_poster(plan, tmp_path):
    seen = []
    result = promo.make_promo(
        plan, api_key="test-key", llm=FakeLLM(good_sns(plan)), out_dir=tmp_path,
        transport=transport((200, {"output_image": {"data": png_b64((900, 1200))}}), seen=seen),
    )  # fmt: skip
    img = Image.open(result.poster_path)
    assert img.size == (1200, 1600) and img.format == "PNG"
    assert result.used_ai_image and not result.image_cropped and result.image_notice is None
    body = json.loads(seen[0].content)
    assert body["model"] == promo.DEFAULT_IMAGE_MODEL
    assert body["response_format"] == {"type": "image", "image_size": "1K", "aspect_ratio": "3:4"}
    assert body["input"] == result.image_prompt
    assert seen[0].headers["x-goog-api-key"] == "test-key"
    assert all(c.ok for c in result.checks), result.checks
    assert result.sns_text and len(result.hashtags) == 5


def test_steps_shaped_response_is_read(plan, tmp_path):
    steps = {"steps": [{"type": "model_output", "content": [{"type": "text", "text": "ok"},
                                                            {"type": "image", "data": png_b64((300, 400))}]}]}  # fmt: skip
    result = promo.make_promo(
        plan, api_key="k", out_dir=tmp_path, transport=transport((200, steps))
    )
    assert result.used_ai_image


def test_ai_credit_only_on_ai_poster():
    texts = {
        "title": "감귤 마켓",
        "period": "12월 중 · 날짜 추후 공지",
        "place": "제주시 애월읍 · 장소 추후 공지",
    }
    gray = Image.new("RGB", (1200, 1600), (128, 128, 128))
    ai = promo.render_poster(texts, gray)
    plain = promo.render_poster(texts, None, (128, 128, 128))
    box = (700, 1535, 1130, 1580)  # 오른쪽 아래 작은 글씨 자리
    assert ai.crop(box).convert("L").getextrema()[0] != ai.crop(box).convert("L").getextrema()[1]
    lo, hi = plain.crop(box).convert("L").getextrema()
    assert lo == hi  # 단색 기본 포스터에는 AI 표기 없음


def test_aspect_ratio_rejected_then_retried_and_cropped(plan, tmp_path):
    seen = []
    result = promo.make_promo(
        plan, api_key="k", out_dir=tmp_path,
        transport=transport(
            (400, {"error": {"message": "aspect_ratio 3:4 is not supported for this model"}}),
            (200, {"output_image": {"data": png_b64((1600, 900))}}),  # 16:9로 옴
            seen=seen,
        ),
    )  # fmt: skip
    assert "aspect_ratio" in json.loads(seen[0].content)["response_format"]
    assert "aspect_ratio" not in json.loads(seen[1].content)["response_format"]
    assert result.used_ai_image and result.image_cropped
    assert Image.open(result.poster_path).size == (1200, 1600)


def test_other_ratio_is_cropped(plan, tmp_path):
    result = promo.make_promo(
        plan, api_key="k", out_dir=tmp_path,
        transport=transport((200, {"output_image": {"data": png_b64((1024, 1024))}})),
    )  # fmt: skip
    assert result.image_cropped and Image.open(result.poster_path).size == (1200, 1600)


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded, limit: 0"}}),
        (403, "Image generation requires billing to be enabled"),
    ],
)
def test_quota_error_makes_plain_poster_with_notice(plan, tmp_path, status, body):
    result = promo.make_promo(
        plan, api_key="k", out_dir=tmp_path, transport=transport((status, body))
    )
    assert not result.used_ai_image
    assert result.image_notice == promo.QUOTA_NOTICE
    assert "AI Studio" in result.image_notice and result.image_prompt
    assert Image.open(result.poster_path).size == (1200, 1600)  # 기본 포스터는 만든다


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
