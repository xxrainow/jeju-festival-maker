"""화면 모양 (Figma 「제주 축제랩」 UI 기준): 색·글꼴 토큰, 상단 로고·단계 탭, 단계 머리글, 배지.

계산과 문장은 app/screen.py, 화면 순서는 streamlit_app.py에 두고 여기에는 모양만 둔다.
HTML은 st.html로 그린다 (st.markdown 목록에 섞이지 않아 화면 테스트의 순서가 바뀌지 않는다).
카드 모양은 st.container(key=...)가 붙이는 CSS 클래스(st-key-<key>)로 입힌다.
"""

from html import escape

from app import screen

# Figma 변수 (99 컴포넌트 · 토큰)
TOKENS = {
    "bg": "#f2f2ef",
    "surface": "#ffffff",
    "surface-2": "#f8f8f6",
    "ink": "#121212",
    "ink-2": "#5c5c5c",
    "ink-3": "#9a9a9a",
    "line": "#e2e2de",
    "accent": "#ff8a3d",
    "accent-soft": "#ffe7d6",
    "sea": "#2f7de1",
    "sea-soft": "#dceafb",
    "pass": "#1e9e5a",
    "pass-soft": "#ddf3e6",
    "warn": "#c98a0c",
    "warn-soft": "#fdf0d2",
    "fail": "#e5484d",
    "fail-soft": "#fce3e3",
    "pending": "#7a808a",
    "pending-soft": "#ecedef",
}
STATUS_TONE = {"pass": "pass", "conditional": "warn", "fail": "fail", "pending": "pending"}
STATUS_WORD = {"pass": "통과", "conditional": "조건부", "fail": "실패", "pending": "데이터 대기"}
# 근거 종류 태그 (Figma Evidence Tag)
EVIDENCE_TONE = {
    "사실": "sea",
    "Agent 해석": "accent",
    "주최 측 주장": "ink",
    "데이터 대기": "pending",
    "가상 데이터": "warn",
}
STEP_TITLES = {
    1: ("어떤 축제를 열고 싶나요?",
        ("전국 축제 트렌드에서 아이디어를 찾고, 제주 데이터로 확인해서 기획서와 홍보물까지 만들어요. "
        "모든 조건은 선택이라 비워둬도 괜찮아요.")),
    2: ("아이디어 3개를 골라왔어요",
        "전국에서 늘고 있는 축제 형식과 제주 재료를 엮었어요. 근거를 보고 하나를 골라주세요."),
    3: ("제주 데이터로 확인했어요",
        "고른 아이디어의 가설을 확인 도구 5개로 살펴봤어요. 실패한 항목은 Agent가 고쳐서 다시 확인해요."),
    4: ("기획서 초안이 나왔어요",
        "근거·가정·미확인 사항을 나눠 적었어요. 최종 승인하면 이 내용 그대로 홍보물을 만들어요."),
    5: ("홍보물 시안이에요",
        ("최종 승인한 기획서로 포스터와 SNS 글(인스타그램)을 만들고, 기획서와 같은지 검사해요. "
        "게시는 직접 해 주세요.")),
}  # fmt: skip

_FONT = (
    '"42dot Sans", Pretendard, "Apple SD Gothic Neo", "Noto Sans KR", "Malgun Gothic", sans-serif'
)
_PIXEL = '"Silkscreen", ui-monospace, "SFMono-Regular", Menlo, monospace'


def _vars() -> str:
    return "".join(f"--fl-{k}:{v};" for k, v in TOKENS.items())


CSS = f"""
<style>
:root {{ {_vars()} }}
html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"] {{
  font-family: {_FONT};
}}
[data-testid="stAppViewContainer"] {{ background: var(--fl-bg); color: var(--fl-ink); }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stAppDeployButton"] {{ display: none; }}
[data-testid="stMainBlockContainer"] {{ max-width: 1280px; padding-top: 3rem; padding-bottom: 4rem; }}
[data-testid="stSidebar"] {{ background: var(--fl-surface-2); }}
h1, h2, h3, h4 {{ font-family: {_FONT}; letter-spacing: -0.02em; color: var(--fl-ink); }}
[data-testid="stCaptionContainer"] {{ color: var(--fl-ink-3); }}

/* 화면 읽기 프로그램용 글 (눈에는 상단 탭·칩으로 보인다) */
.st-key-sr-only {{
  position: absolute !important; width: 1px !important; height: 1px !important;
  overflow: hidden !important; clip: rect(0 0 0 0) !important; white-space: nowrap !important;
}}

/* 상단 로고 · 단계 탭 */
.fl-nav {{ display: flex; align-items: center; justify-content: space-between; gap: 16px;
  flex-wrap: wrap; margin-bottom: 8px; }}
.fl-logo {{ display: flex; align-items: center; gap: 10px; }}
.fl-blob {{ width: 30px; height: 30px; border-radius: 50%;
  background: radial-gradient(circle at 40% 40%, #ffd166 0%, #ff8a3d 55%, #ffc9b5 100%);
  box-shadow: 0 0 18px rgba(255, 138, 61, .45); }}
.fl-logo b {{ display: block; font-size: 15px; font-weight: 700; }}
.fl-logo small {{ display: block; font-family: {_PIXEL}; font-size: 9px; letter-spacing: .18em;
  color: var(--fl-ink-2); }}
.fl-steps {{ display: flex; gap: 4px; background: var(--fl-ink); padding: 5px; border-radius: 16px;
  flex-wrap: wrap; }}
.fl-tab {{ padding: 8px 14px; border-radius: 12px; font-size: 13px; color: #8d8d8d; white-space: nowrap; }}
.fl-tab.done {{ color: #ffffff; }}
.fl-tab.done::before {{ content: "✓ "; color: var(--fl-accent); }}
.fl-tab.active {{ background: var(--fl-accent); color: var(--fl-ink); font-weight: 600; }}
.fl-ai {{ font-size: 12px; background: var(--fl-surface); border: 1px solid var(--fl-line);
  border-radius: 999px; padding: 6px 12px; }}

/* 단계 머리글 */
.fl-head {{ margin: 28px 0 8px; }}
[class*="st-key-back_"] + div .fl-head, .fl-head.near {{ margin-top: 8px; }}
.fl-eyebrow {{ font-family: {_PIXEL}; font-size: 11px; letter-spacing: .2em; color: var(--fl-ink-2);
  display: flex; align-items: center; gap: 8px; text-transform: uppercase; }}
.fl-eyebrow::before {{ content: ""; width: 8px; height: 8px; background: var(--fl-accent); }}
.fl-eyebrow span {{ font-family: {_FONT}; letter-spacing: 0; text-transform: none; }}
.fl-h1 {{ font-size: 40px; font-weight: 700; letter-spacing: -0.03em; margin: 10px 0 8px; line-height: 1.2; }}
.fl-desc {{ font-size: 16px; color: var(--fl-ink-2); max-width: 780px; margin: 0; }}

/* 칩 · 배지 · 근거 태그 */
.fl-chips {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0 4px; }}
.fl-chip {{ font-size: 12px; padding: 6px 12px; border-radius: 999px; background: var(--fl-ink);
  color: #fff; }}
.fl-chip.light {{ background: var(--fl-surface); color: var(--fl-ink); border: 1px solid var(--fl-line); }}
.fl-badge {{ display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 500;
  padding: 4px 10px; border-radius: 999px; }}
.fl-badge::before {{ content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }}
{"".join(f".fl-badge.{t} {{ color: var(--fl-{t}); background: var(--fl-{t}-soft); }}" for t in ("pass", "warn", "fail", "pending"))}
.fl-tag {{ display: inline-flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 600;
  padding: 3px 8px; border-radius: 6px; margin-bottom: 2px; }}
.fl-tag::before {{ content: ""; width: 6px; height: 6px; border-radius: 2px; background: currentColor; }}
.fl-tag.sea {{ color: var(--fl-sea); background: var(--fl-sea-soft); }}
.fl-tag.accent {{ color: #c4561a; background: var(--fl-accent-soft); }}
.fl-tag.ink {{ color: var(--fl-ink); background: var(--fl-pending-soft); }}
.fl-tag.pending {{ color: var(--fl-pending); background: var(--fl-pending-soft); }}
.fl-tag.warn {{ color: var(--fl-warn); background: var(--fl-warn-soft); }}
.fl-format {{ display: inline-block; font-size: 12px; padding: 5px 12px; border-radius: 999px;
  border: 1px solid var(--fl-line); background: var(--fl-surface-2); margin-bottom: 4px; }}

/* 확인 결과 요약 줄 */
.fl-summary {{ display: flex; align-items: center; gap: 18px; flex-wrap: wrap; background: var(--fl-surface);
  border: 1px solid var(--fl-line); border-radius: 24px; padding: 14px 20px; margin: 8px 0 4px; }}
.fl-summary .count {{ font-size: 13px; color: var(--fl-ink-2); display: flex; gap: 6px; align-items: center; }}
.fl-summary .count b {{ font-size: 16px; color: var(--fl-ink); }}
.fl-check-head {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }}
.fl-check-head b {{ font-size: 18px; }}
.fl-section {{ font-family: {_PIXEL}; font-size: 11px; letter-spacing: .2em; color: var(--fl-ink-3);
  margin: 26px 0 6px; text-transform: uppercase; }}

/* 카드 (st.container(key=...)) */
[class*="st-key-card"], [class*="st-key-res-"], [class*="st-key-chg-"], .st-key-doc {{
  background: var(--fl-surface); border: 1px solid var(--fl-line); border-radius: 24px;
  padding: 22px 24px; box-shadow: 0 1px 2px rgba(18, 18, 18, .03);
}}
[class*="st-key-res-fail"] {{ border: 2px solid var(--fl-fail); }}
[class*="st-key-chg-"] {{ border-left: 6px solid var(--fl-accent); }}
[class*="st-key-soft"] {{ background: var(--fl-surface-2); border-radius: 16px; padding: 14px 16px; }}
.st-key-doc {{ padding: 32px 40px; }}

/* 버튼 */
button[data-testid^="stBaseButton"] {{ border-radius: 999px; font-weight: 600; min-height: 44px;
  padding-left: 20px; padding-right: 20px; }}
button[data-testid="stBaseButton-primary"] {{ background: var(--fl-accent); border-color: var(--fl-accent);
  color: var(--fl-ink); }}
button[data-testid="stBaseButton-primary"]:hover {{ background: #ff7a22; border-color: #ff7a22;
  color: var(--fl-ink); }}
button[data-testid="stBaseButton-secondary"] {{ background: var(--fl-surface); border: 1px solid var(--fl-ink);
  color: var(--fl-ink); }}
button[data-testid$="FormSubmit"], [class*="st-key-pick_"] button {{ background: var(--fl-ink);
  border-color: var(--fl-ink); color: #fff; }}
button[data-testid$="FormSubmit"]:hover, [class*="st-key-pick_"] button:hover {{ background: #2b2b2b;
  border-color: #2b2b2b; color: #fff; }}
[class*="st-key-back_"] {{ margin-top: 18px; margin-bottom: -18px; }}
[class*="st-key-back_"] button {{ background: var(--fl-surface); border: 1px solid var(--fl-line);
  color: var(--fl-ink-2); min-height: 34px; padding: 4px 14px; font-size: 13px; font-weight: 500; }}
[class*="st-key-back_"] button:hover {{ border-color: var(--fl-ink); color: var(--fl-ink);
  background: var(--fl-surface); }}

/* 입력 · 알림 · 접기 · 표 */
[data-testid="stForm"] {{ padding: 0; }}
[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] {{ border-radius: 12px; }}
[data-testid="stAlert"] > div {{ border-radius: 16px; }}
[data-testid="stExpander"] details {{ background: var(--fl-surface); border: 1px solid var(--fl-line);
  border-radius: 16px; }}
[data-testid="stDataFrame"] {{ border-radius: 12px; overflow: hidden; }}
[data-testid="stCode"] pre {{ border-radius: 12px; }}
/* 01-1 첫 화면 */
.fl-hero {{ display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 24px;
  margin: 36px 0 12px; }}
.fl-hero .side small {{ display: block; font-family: {_PIXEL}; font-size: 11px; letter-spacing: .2em;
  color: var(--fl-ink-2); margin-bottom: 6px; }}
.fl-hero .side b {{ font-size: clamp(40px, 5.6vw, 76px); font-weight: 800; letter-spacing: -0.04em;
  line-height: 1.05; }}
.fl-hero .side.right {{ text-align: right; }}
.fl-orb {{ position: relative; width: 260px; height: 260px; }}
.fl-orb .sq {{ position: absolute; inset: 0; border-radius: 34%;
  background: linear-gradient(135deg, #ffd84d 0%, #ff8a3d 50%, #ff6f8a 100%);
  box-shadow: 0 30px 80px rgba(255, 138, 61, .35); }}
.fl-orb .hole {{ position: absolute; inset: 44px; border-radius: 50%; background: #fff; }}
.fl-orb .plus {{ position: absolute; left: 50%; top: 50%; width: 70px; height: 70px;
  transform: translate(-50%, -50%);
  background:
    linear-gradient(var(--fl-accent), var(--fl-accent)) 50% 0 / 10px 20px no-repeat,
    linear-gradient(var(--fl-accent), var(--fl-accent)) 50% 100% / 10px 20px no-repeat,
    linear-gradient(var(--fl-accent), var(--fl-accent)) 0 50% / 20px 10px no-repeat,
    linear-gradient(var(--fl-accent), var(--fl-accent)) 100% 50% / 20px 10px no-repeat; }}
.fl-orb .tag {{ position: absolute; font-size: 12px; background: var(--fl-ink); color: #fff;
  padding: 7px 12px; border-radius: 999px; white-space: nowrap; }}
.fl-hero-desc {{ text-align: center; color: var(--fl-ink-2); font-size: 17px; margin: 22px 0 18px; }}
.st-key-pill {{ background: var(--fl-surface); border-radius: 999px; padding: 8px 10px 8px 22px;
  box-shadow: 0 12px 40px rgba(18, 18, 18, .08); }}
.st-key-pill [data-baseweb="input"] {{ background: transparent; border: none; }}
.st-key-pill input {{ font-size: 16px; }}
.st-key-pill [data-baseweb="base-input"], .st-key-pill input,
[class*="st-key-fieldcard"] [data-baseweb="base-input"], [class*="st-key-fieldcard"] input,
[class*="st-key-fieldcard"] [data-baseweb="select"] div,
[class*="st-key-fieldcard"] .react-aria-ComboBox > div,
.st-key-pill [data-testid="stTextInputRootElement"],
[class*="st-key-fieldcard"] [data-testid="stTextInputRootElement"],
[class*="st-key-fieldcard"] [data-testid="stNumberInputContainer"] {{
  background: transparent !important; border-color: transparent !important; }}

/* 01-2 문장 띠 · 조건 칸 카드 */
.fl-quote {{ display: flex; align-items: center; gap: 14px; background: var(--fl-ink); color: #fff;
  border-radius: 999px; padding: 18px 28px; font-size: 16px; margin: 18px 0 14px; }}
.fl-quote::before {{ content: "✦"; color: var(--fl-accent); }}
[class*="st-key-fieldcard"] {{ background: var(--fl-surface); border: 1px solid var(--fl-line);
  border-radius: 20px; padding: 14px 18px 12px; gap: 4px; }}
[class*="st-key-fieldcard"] [data-baseweb="input"], [class*="st-key-fieldcard"] [data-baseweb="select"] > div,
[class*="st-key-fieldcard"] [data-testid="stNumberInputContainer"] {{ background: transparent; border: none; }}
[class*="st-key-fieldcard"] input, [class*="st-key-fieldcard"] [data-baseweb="select"] {{
  font-size: 19px; font-weight: 600; color: var(--fl-ink); }}
[class*="st-key-fieldcard"] input {{ padding-left: 0; }}
.fl-field-head {{ display: flex; justify-content: space-between; font-size: 13px; color: var(--fl-ink-2); }}
.fl-field-head .ai {{ color: var(--fl-accent); }}
.fl-field-head .empty {{ color: var(--fl-ink-3); }}
/* 01-1 예시 카드 (꾸밈용, 누를 수 없음) */
.fl-examples {{ display: flex; justify-content: center; margin: 0 auto -6px; max-width: 980px; }}
.fl-ex {{ flex: 1; background: var(--fl-surface); border-radius: 16px; padding: 22px 18px 18px;
  margin: 0 -6px; box-shadow: 0 10px 30px rgba(18, 18, 18, .07); border-top: 10px solid; pointer-events: none; }}
.fl-ex small {{ display: block; color: var(--fl-ink-3); font-size: 11px; margin-bottom: 6px; }}
.fl-ex b {{ display: block; font-size: 15px; margin-bottom: 6px; }}
.fl-ex span {{ font-size: 12px; color: var(--fl-ink-2); }}

/* 02-1 아이디어 만드는 중 */
.fl-work {{ background: var(--fl-surface); border: 1px solid var(--fl-line); border-radius: 24px;
  padding: 26px 28px; margin-top: 18px; max-width: 760px; }}
.fl-work .title {{ font-size: 13px; font-weight: 600; color: var(--fl-ink-2); margin-bottom: 10px; }}
.fl-row {{ display: flex; align-items: center; gap: 14px; padding: 14px 0; border-top: 1px solid var(--fl-line); }}
.fl-row:first-of-type {{ border-top: none; }}
.fl-row .dot {{ width: 22px; height: 22px; border-radius: 50%; border: 2px solid var(--fl-line); flex: none;
  display: flex; align-items: center; justify-content: center; font-size: 12px; color: #fff; }}
.fl-row.done .dot {{ background: var(--fl-pass); border-color: var(--fl-pass); }}
.fl-row.done .dot::before {{ content: "✓"; }}
.fl-row.active .dot {{ border-color: var(--fl-accent); border-top-color: transparent;
  animation: fl-spin .9s linear infinite; }}
@keyframes fl-spin {{ to {{ transform: rotate(360deg); }} }}
.fl-row .txt {{ flex: 1; }}
.fl-row .txt b {{ display: block; font-size: 15px; font-weight: 600; }}
.fl-row .txt span {{ font-size: 12px; color: var(--fl-ink-3); }}
.fl-row.todo .txt b {{ color: var(--fl-ink-3); }}
.fl-row .eng {{ font-size: 12px; border: 1px solid var(--fl-line); border-radius: 999px; padding: 4px 12px; }}
.st-key-foot {{ margin-top: 32px; padding-top: 16px; border-top: 1px solid var(--fl-line); }}
</style>
"""


def nav_html(step: int, has_llm: bool) -> str:
    """로고 + 단계 캡슐 탭 (보여주기만, 누르는 기능 없음) + AI 설정 상태."""
    tabs = []
    for i, name in enumerate(screen.STEPS, start=1):
        cls = "active" if i == step else "done" if i < step else ""
        tabs.append(f'<span class="fl-tab {cls}">{i:02d} {escape(name)}</span>')
    ai = "● AI 연결됨" if has_llm else "○ AI 설정 없음"
    return (
        '<div class="fl-nav"><div class="fl-logo"><span class="fl-blob"></span>'
        "<div><b>제주 축제랩</b><small>JEJU FESTA MAKER</small></div></div>"
        f'<div class="fl-steps">{"".join(tabs)}</div><span class="fl-ai">{ai}</span></div>'
    )


def head_html(step: int, title: str | None = None, desc: str | None = None) -> str:
    """STEP 0n / 05 — 단계 이름 + 큰 제목 + 설명."""
    default_title, default_desc = STEP_TITLES[step]
    name = screen.STEPS[step - 1]
    return (
        f'<div class="fl-head"><div class="fl-eyebrow">STEP {step:02d} / {len(screen.STEPS):02d}'
        f" — <span>{escape(name)}</span></div>"
        f'<div class="fl-h1">{escape(title or default_title)}</div>'
        f'<p class="fl-desc">{escape(desc or default_desc)}</p></div>'
    )


def chips_html(words: list[str], light_from: int | None = None) -> str:
    out = []
    for i, w in enumerate(words):
        cls = "fl-chip light" if light_from is not None and i >= light_from else "fl-chip"
        out.append(f'<span class="{cls}">{escape(w)}</span>')
    return f'<div class="fl-chips">{"".join(out)}</div>'


def request_chips(request) -> str:
    """고른 조건 칩. 정하지 않은 조건은 흰 칩."""
    filled = [
        ("#" + request.region) if request.region else None,
        ("#" + request.purpose) if request.purpose else None,
        ("#" + request.interest) if request.interest else None,
        ("#" + request.season) if request.season else None,
        ("#" + request.target) if request.target else None,
        f"#예산 {screen.won(request.budget_max_krw)}" if request.budget_max_krw else None,
    ]
    empty = [
        name
        for name, value in [
            ("지역 전체", request.region),
            ("목적 미정", request.purpose),
            ("소재 미정", request.interest),
            ("계절 미정", request.season),
            ("대상 미정", request.target),
            ("예산 미정", request.budget_max_krw),
        ]
        if not value
    ]
    words = [w for w in filled if w]
    return chips_html(words + empty, light_from=len(words))


def badge_html(status: str) -> str:
    return f'<span class="fl-badge {STATUS_TONE[status]}">{STATUS_WORD[status]}</span>'


def tag_html(kind: str) -> str:
    return f'<span class="fl-tag {EVIDENCE_TONE[kind]}">{escape(kind)}</span>'


def check_head_html(label: str, status: str, synthetic: bool) -> str:
    extra = " " + tag_html("가상 데이터") if synthetic else ""
    return (
        f'<div class="fl-check-head"><b>{escape(label)}</b>'
        f"<span>{badge_html(status)}{extra}</span></div>"
    )


def summary_html(results, note: str) -> str:
    """확인 결과 요약 줄: 항목별 배지 + 통과·조건부·실패 개수."""
    items = "".join(
        f'<span class="count">{escape(screen.CHECK_LABELS[r.check])} {badge_html(r.status)}</span>'
        for r in results
    )
    return f'<div class="fl-summary">{items}<span class="count">{escape(note)}</span></div>'


def section_html(label: str) -> str:
    return f'<div class="fl-section">{escape(label)}</div>'


def format_html(text: str) -> str:
    return f'<span class="fl-format">{escape(text)}</span>'


HERO = (
    '<div class="fl-hero">'
    '<div class="side"><small>PLAN YOUR</small><b>우리 동네</b></div>'
    '<div class="fl-orb"><div class="sq"></div><div class="hole"></div><div class="plus"></div>'
    '<span class="tag" style="left:-30px;top:-14px">#애월 감귤</span>'
    '<span class="tag" style="right:-50px;top:40px">#대정 방어</span>'
    '<span class="tag" style="right:-6px;bottom:-16px">#성산 유채</span></div>'
    '<div class="side right"><small>FESTA LAB</small><b>축제 만들기</b></div></div>'
    '<p class="fl-hero-desc">전국 축제 트렌드에서 아이디어를 찾고, 제주 데이터로 확인해서 '
    "기획서와 홍보물까지 만들어요.</p>"
    '<div class="fl-examples" aria-hidden="true">'
    + "".join(
        f'<div class="fl-ex" style="border-top-color:{color};transform:rotate({tilt}deg)">'
        f"<small>예시</small><b>{name}</b><span>{meta}</span></div>"
        for name, meta, color, tilt in (
            ("애월 감귤 마켓", "겨울 · 가족 · 1천만 원", "#ff8a3d", -2),
            ("대정 방어 축제", "겨울 · 상권 활성화", "#2f7de1", 1.5),
            ("성산 유채꽃 산책", "봄 · 관광객 유치", "#ffd84d", -1),
            ("해녀 야시장", "여름 · 청년", "#ffc9b5", 1.5),
            ("마을 귤꽃 음악회", "봄 · 주민 참여", "#1e9e5a", -1.5),
        )
    )
    + "</div>"
)

# 02-1 아이디어 만드는 중: (제목, 처음 설명, 엔진)
IDEA_STEPS = (
    ("전국 축제 트렌드 계산", "문체부 2024–2026 개최계획에서 형식별 신설 수를 세요", "코드"),
    ("형식 × 제주 재료 조합 점수", "계절·목적에 맞는 후보만 남겨요", "코드"),
    ("3개 고르고 카드 문장 쓰기", "수치는 바꾸지 않고 설명만 써요", "AI"),
    ("확인할 가설 정리", "고르면 제주 데이터로 확인할 것 2개씩", "코드"),
)


def progress_html(current: int, details: dict[int, str]) -> str:
    """진행 상황 목록. current 단계는 도는 중, 앞 단계는 완료, 뒤 단계는 대기."""
    rows = []
    for i, (title, desc, engine) in enumerate(IDEA_STEPS, start=1):
        state = "done" if i < current else "active" if i == current else "todo"
        rows.append(
            f'<div class="fl-row {state}"><span class="dot"></span>'
            f'<div class="txt"><b>{escape(title)}</b><span>{escape(details.get(i, desc))}</span></div>'
            f'<span class="eng">{engine}</span></div>'
        )
    return f'<div class="fl-work"><div class="title">진행 상황</div>{"".join(rows)}</div>'


def quote_html(sentence: str) -> str:
    """01-2 맨 위 검은 띠: 사용자가 적은 문장."""
    return f'<div class="fl-quote">“{escape(sentence)}”</div>'


def field_origin(value, from_ai: bool) -> tuple[str, str]:
    """조건 칸 오른쪽 표시: (글, CSS 클래스)."""
    if value in (None, ""):
        return "비어 있음", "empty"
    return ("AI가 채움", "ai") if from_ai else ("입력함", "empty")


def field_head_html(label: str, origin: tuple[str, str]) -> str:
    text, cls = origin
    return (
        f'<div class="fl-field-head"><span>{escape(label)}</span>'
        f'<span class="{cls}">{escape(text)}</span></div>'
    )
