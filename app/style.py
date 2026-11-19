"""화면 모양 (Figma 「제주 축제랩」 UI 기준): 색·글꼴 토큰, 상단 로고·단계 탭, 단계 머리글, 배지.

계산과 문장은 app/screen.py, 화면 순서는 streamlit_app.py에 두고 여기에는 모양만 둔다.
HTML은 st.html로 그린다 (st.markdown 목록에 섞이지 않아 화면 테스트의 순서가 바뀌지 않는다).
카드 모양은 st.container(key=...)가 붙이는 CSS 클래스(st-key-<key>)로 입힌다.
"""

from base64 import b64encode
from html import escape
from pathlib import Path

from app import screen

_BRAND_MARK_URI = "data:image/png;base64," + b64encode(
    (Path(__file__).resolve().parents[1] / "assets" / "brand-mark.png").read_bytes()
).decode("ascii")


def _icon_uri(name: str) -> str:
    path = Path(__file__).resolve().parents[1] / "assets" / "icons" / f"{name}.svg"
    return "data:image/svg+xml;base64," + b64encode(path.read_bytes()).decode("ascii")

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
    "데이터": "sea",
    "에이전트 해석": "accent",
    "참고 수치": "ink",
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
        "고른 아이디어의 가설을 확인 도구 5개로 살펴봤어요. 실패한 항목은 에이전트가 고쳐서 다시 확인해요."),
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

/* Streamlit 기본 글씨도 90%로 조정한다. rem 기준과 컨테이너 여백은 유지한다. */
[data-testid="stMarkdownContainer"] {{ font-size: 14.4px; }}
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stWidgetLabel"] p,
[data-testid="stExpander"] summary p {{ font-size: 14.4px; }}
[data-testid="stMarkdownContainer"] h1 {{ font-size: 39.6px; }}
[data-testid="stMarkdownContainer"] h2 {{ font-size: 32.4px; }}
[data-testid="stMarkdownContainer"] h3 {{ font-size: 25.2px; }}
[data-testid="stMarkdownContainer"] h4 {{ font-size: 21.6px; }}
[data-testid="stCaptionContainer"] p {{ font-size: 12.6px; }}
[data-testid="stAppViewContainer"] input,
[data-testid="stAppViewContainer"] textarea,
[data-baseweb="select"], [data-baseweb="select"] input,
[data-baseweb="select"] span, [data-baseweb="select"] div,
[data-baseweb="menu"] li {{ font-size: 14.4px; }}
[data-testid="stCode"] code {{ font-size: 12.6px; }}

/* 화면 읽기 프로그램용 글 (눈에는 상단 탭·칩으로 보인다) */
.st-key-sr-only {{
  position: absolute !important; width: 1px !important; height: 1px !important;
  overflow: hidden !important; clip: rect(0 0 0 0) !important; white-space: nowrap !important;
}}

/* 상단 로고 · 단계 탭 */
.fl-nav {{ display: flex; align-items: center; justify-content: space-between; gap: 16px;
  flex-wrap: wrap; margin-bottom: 8px; }}
.fl-logo {{ display: flex; align-items: center; gap: 10px; }}
.fl-blob {{ display: block; width: 36px; height: 30px; flex: none; object-fit: contain; }}
.fl-logo b {{ display: block; font-size: 13.5px; font-weight: 700; }}
.fl-logo small {{ display: block; font-family: {_PIXEL}; font-size: 8.1px; letter-spacing: .18em;
  color: var(--fl-ink-2); }}
.fl-steps {{ display: flex; gap: 4px; background: var(--fl-ink); padding: 5px; border-radius: 16px;
  flex-wrap: wrap; }}
.fl-tab {{ padding: 8px 14px; border-radius: 12px; font-size: 11.7px; color: #8d8d8d; white-space: nowrap; }}
.fl-tab.done {{ color: #ffffff; }}
.fl-tab.done::before {{ content: "✓ "; color: var(--fl-accent); }}
.fl-tab.active {{ background: var(--fl-accent); color: var(--fl-ink); font-weight: 600; }}
.fl-nav::after {{ content: ""; width: 84px; flex: none; }}
@media (max-width: 900px) {{ .fl-nav::after {{ display: none; }} }}

/* 접어 두는 설정 패널 */
[data-testid="stSidebar"] {{ border-right: 1px solid var(--fl-line); }}
[data-testid="stSidebarUserContent"] {{ padding: 0px 24px 32px; }}
.fl-settings {{ color: var(--fl-ink); font-family: {_FONT}; display: flex;
  flex-direction: column; min-height: calc(100dvh - 96px); }}
.fl-settings > * {{ flex-shrink: 0; }}
.fl-settings-eyebrow {{ font-family: {_PIXEL}; font-size: 9px; letter-spacing: .18em;
  color: var(--fl-ink-3); margin-bottom: 8px; }}
.fl-settings h2 {{ font-size: 25.2px; font-weight: 700; letter-spacing: -.04em; margin: 0 0 10px;
  padding: 0; line-height: 1.25; }}
.fl-settings-intro {{ font-size: 11.7px; color: var(--fl-ink-2); margin: 0 0 24px; line-height: 1.6; }}
.fl-settings-card {{ padding: 20px; border: 1px solid var(--fl-line); border-radius: 20px;
  background: var(--fl-surface); }}
.fl-settings-label {{ display: flex; justify-content: space-between; align-items: center; gap: 8px;
  font-size: 10.8px; color: var(--fl-ink-2); margin-bottom: 18px; }}
.fl-settings-state {{ display: inline-flex; align-items: center; gap: 6px; padding: 4px 8px;
  border-radius: 999px; background: var(--fl-accent-soft); color: #a44816; font-size: 9.9px; }}
.fl-settings-state::before {{ content: ""; width: 5px; height: 5px; border-radius: 50%;
  background: var(--fl-accent); }}
.fl-settings-state.off {{ background: var(--fl-pending-soft); color: var(--fl-pending); }}
.fl-settings-state.off::before {{ background: var(--fl-pending); }}
.fl-settings-card h3 {{ font-size: 16.2px; margin: 0px 0 8px; padding: 0; letter-spacing: -.03em; }}
.fl-settings-card p {{ font-size: 11.7px; line-height: 1.75; color: var(--fl-ink-2); margin: 0; }}
.fl-settings-guide {{ margin-top: auto; padding-top: 48px; margin-bottom: 48px; }}
.fl-settings-guide h3 {{ font-size: 10.8px; font-weight: 600; color: var(--fl-ink-2);
  padding: 0; margin: 0 0 14px; }}
.fl-settings-guide ol {{ list-style: none; padding: 0; margin: 0; display: grid; gap: 14px; }}
.fl-settings-guide li {{ display: flex; align-items: center; gap: 10px; font-size: 11.7px;
  color: var(--fl-ink-2); }}
.fl-settings-guide li span {{ display: inline-flex; align-items: center; justify-content: center;
  width: 24px; height: 24px; flex: none; background: var(--fl-surface); border: 1px solid var(--fl-line);
  border-radius: 8px; font-size: 9px; color: var(--fl-ink-3); }}
.fl-settings-foot {{ margin: 0; padding-top: 18px; margin-bottom: 48px; border-top: 1px solid var(--fl-line);
  font-size: 9.9px; line-height: 1.8; color: var(--fl-ink-3); }}

/* 단계 머리글 */
.fl-head {{ margin: 28px 0 8px; }}
[class*="st-key-back_"] + div .fl-head {{ margin-top: 20px; }}
.fl-head.near {{ margin-top: 8px; }}
.fl-eyebrow {{ font-family: {_PIXEL}; font-size: 9.9px; letter-spacing: .2em; color: var(--fl-ink-2);
  display: flex; align-items: center; gap: 8px; text-transform: uppercase; }}
.fl-eyebrow::before {{ content: ""; width: 8px; height: 8px; background: var(--fl-accent); }}
.fl-eyebrow span {{ font-family: {_FONT}; letter-spacing: 0; text-transform: none; }}
.fl-h1 {{ font-size: 36px; font-weight: 700; letter-spacing: -0.03em; margin: 10px 0 8px; line-height: 1.2; }}
.fl-desc {{ font-size: 14.4px; color: var(--fl-ink-2); max-width: 780px; margin: 0; }}

/* 칩 · 배지 · 근거 태그 */
.fl-chips {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0 4px; }}
.fl-chip {{ font-size: 10.8px; padding: 6px 12px; border-radius: 999px; background: var(--fl-ink);
  color: #fff; }}
.fl-chip.light {{ background: var(--fl-surface); color: var(--fl-ink); border: 1px solid var(--fl-line); }}
.fl-badge {{ display: inline-flex; align-items: center; gap: 6px; font-size: 10.8px; font-weight: 500;
  padding: 4px 10px; border-radius: 999px; }}
.fl-badge::before {{ content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }}
{"".join(f".fl-badge.{t} {{ color: var(--fl-{t}); background: var(--fl-{t}-soft); }}" for t in ("pass", "warn", "fail", "pending"))}
.fl-tag {{ display: inline-flex; align-items: center; gap: 5px; font-size: 9.9px; font-weight: 600;
  padding: 3px 8px; border-radius: 6px; margin-bottom: 2px; }}
.fl-tag::before {{ content: ""; width: 6px; height: 6px; border-radius: 2px; background: currentColor; }}
.fl-tag.sea {{ color: var(--fl-sea); background: var(--fl-sea-soft); }}
.fl-tag.accent {{ color: #c4561a; background: var(--fl-accent-soft); }}
.fl-tag.ink {{ color: var(--fl-ink); background: var(--fl-pending-soft); }}
.fl-tag.pending {{ color: var(--fl-pending); background: var(--fl-pending-soft); }}
.fl-tag.warn {{ color: var(--fl-warn); background: var(--fl-warn-soft); }}
.fl-format {{ display: inline-block; font-size: 10.8px; padding: 5px 12px; border-radius: 999px;
  border: 1px solid var(--fl-line); background: var(--fl-surface-2); margin-bottom: 4px; }}

.fl-check-head {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }}
.fl-check-head b {{ font-size: 16.2px; }}
.fl-section {{ font-family: {_PIXEL}; font-size: 9.9px; letter-spacing: .2em; color: var(--fl-ink-3);
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
[class*="st-key-back_"] {{ margin-top: 18px; margin-bottom: 0; }}
[class*="st-key-back_"] button {{ background: transparent; border: 0; border-radius: 4px;
  box-shadow: none; color: var(--fl-ink-2); min-height: 28px; padding: 2px 0;
  font-size: 11.7px; font-weight: 400; }}
[class*="st-key-back_"] button p {{ font-size: inherit; font-weight: inherit; }}
[class*="st-key-back_"] button:hover {{ color: var(--fl-ink); background: transparent;
  text-decoration: underline; text-underline-offset: 3px; }}
[class*="st-key-back_"] button:focus-visible {{ outline: 2px solid var(--fl-accent);
  outline-offset: 4px; }}

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
.fl-hero .side small {{ display: block; font-family: {_PIXEL}; font-size: 9.9px; letter-spacing: .2em;
  color: var(--fl-ink-2); margin-bottom: 6px; }}
.fl-hero .side b {{ font-size: clamp(36px, 5.04vw, 68.4px); font-weight: 800; letter-spacing: -0.04em;
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
.fl-orb .tag {{ position: absolute; font-size: 10.8px; background: var(--fl-ink); color: #fff;
  padding: 7px 12px; border-radius: 999px; white-space: nowrap; }}
.fl-hero-desc {{ text-align: center; color: var(--fl-ink-2); font-size: 15.3px; margin: 22px 0 18px; }}
.st-key-pill {{ background: var(--fl-surface); border-radius: 999px; padding: 8px 10px 8px 22px;
  box-shadow: 0 12px 40px rgba(18, 18, 18, .08); }}
.st-key-pill [data-baseweb="input"] {{ background: transparent; border: none; }}
.st-key-pill input {{ font-size: 14.4px; }}
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
  border-radius: 999px; padding: 18px 28px; font-size: 14.4px; margin: 18px 0 14px; }}
.fl-quote::before {{ content: "✦"; color: var(--fl-accent); }}
[class*="st-key-fieldcard"] {{ background: var(--fl-surface); border: 1px solid var(--fl-line);
  border-radius: 20px; padding: 14px 18px 12px; gap: 4px; }}
[class*="st-key-fieldcard"] [data-baseweb="input"], [class*="st-key-fieldcard"] [data-baseweb="select"] > div,
[class*="st-key-fieldcard"] [data-testid="stNumberInputContainer"] {{ background: transparent; border: none; }}
[class*="st-key-fieldcard"] input, [class*="st-key-fieldcard"] [data-baseweb="select"] {{
  font-size: 17.1px; font-weight: 600; color: var(--fl-ink); }}
[class*="st-key-fieldcard"] input {{ padding-left: 0; }}
.fl-field-head {{ display: flex; justify-content: space-between; font-size: 11.7px; color: var(--fl-ink-2); }}
.fl-field-head .ai {{ color: var(--fl-accent); }}
.fl-field-head .empty {{ color: var(--fl-ink-3); }}
/* 01-1 예시 카드 (꾸밈용, 누를 수 없음) */
.fl-examples {{ display: flex; justify-content: center; margin: 0 auto -6px; max-width: 980px; }}
.fl-ex {{ flex: 1; background: var(--fl-surface); border-radius: 16px; padding: 22px 18px 18px;
  margin: 0 -6px; box-shadow: 0 10px 30px rgba(18, 18, 18, .07); border-top: 10px solid; pointer-events: none; }}
.fl-ex small {{ display: block; color: var(--fl-ink-3); font-size: 9.9px; margin-bottom: 6px; }}
.fl-ex b {{ display: block; font-size: 13.5px; margin-bottom: 6px; }}
.fl-ex span {{ font-size: 10.8px; color: var(--fl-ink-2); }}

/* 02-1 아이디어 만드는 중 */
.fl-work {{ background: var(--fl-surface); border: 1px solid var(--fl-line); border-radius: 24px;
  padding: 26px 28px; margin-top: 18px; max-width: 760px; }}
.fl-work .title {{ font-size: 11.7px; font-weight: 600; color: var(--fl-ink-2); margin-bottom: 10px; }}
.fl-row {{ display: flex; align-items: center; gap: 14px; padding: 14px 0; border-top: 1px solid var(--fl-line); }}
.fl-row:first-of-type {{ border-top: none; }}
.fl-row .dot {{ width: 22px; height: 22px; border-radius: 50%; border: 2px solid var(--fl-line); flex: none;
  display: flex; align-items: center; justify-content: center; font-size: 10.8px; color: #fff; }}
.fl-row.done .dot {{ background: var(--fl-pass); border-color: var(--fl-pass); }}
.fl-row.done .dot::before {{ content: "✓"; }}
.fl-row.active .dot {{ border-color: var(--fl-accent); border-top-color: transparent;
  animation: fl-spin .9s linear infinite; }}
@keyframes fl-spin {{ to {{ transform: rotate(360deg); }} }}
.fl-row .txt {{ flex: 1; }}
.fl-row .txt b {{ display: block; font-size: 13.5px; font-weight: 600; }}
.fl-row .txt span {{ font-size: 10.8px; color: var(--fl-ink-3); }}
.fl-row.todo .txt b {{ color: var(--fl-ink-3); }}
.fl-row .eng {{ font-size: 10.8px; border: 1px solid var(--fl-line); border-radius: 999px; padding: 4px 12px; }}
.fl-evidence-legend {{ display: flex; align-items: center; flex-wrap: wrap; gap: 12px 20px;
  margin-top: 28px; font-family: {_FONT}; font-size: 10.8px; color: var(--fl-ink-2); }}
.fl-evidence-legend > span {{ display: inline-flex; align-items: center; flex-wrap: wrap;
  gap: 8px; line-height: 1.7; }}
.fl-evidence-legend .fl-tag {{ margin: 0; flex-shrink: 0; }}
.st-key-foot {{ margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--fl-line); }}

/* 02 아이디어: 조건과 편집 동작을 묶고, 세 카드를 같은 높이로 표시한다. */
.st-key-idea-nav {{ margin-bottom: 8px; }}
.st-key-idea-step-tabs {{ background: var(--fl-ink); padding: 5px; border-radius: 16px; }}
.st-key-idea-step-tabs > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {{
  gap: 4px; align-items: center;
}}
.st-key-idea-step-tabs button {{
  font-family: {_FONT};
  display: inline-flex; align-items: center; justify-content: center; box-sizing: border-box;
  height: 34.72px; min-height: 34.72px; padding: 8px 14px; border-radius: 12px;
  font-size: 11.7px; line-height: 1.6;
}}
.st-key-idea-step-tabs button {{ border: 0; background: transparent; color: white; box-shadow: none; }}
.st-key-idea-step-tabs button [data-testid="stMarkdownContainer"] {{
  display: flex; align-items: center; line-height: 1.6;
}}
.st-key-idea-step-tabs button p {{ font-family: {_FONT}; display: flex; align-items: center; gap: 6px;
  font-size: 11.7px; line-height: 1.6; font-weight: 400; color: inherit; white-space: nowrap; margin: 0; }}
.st-key-idea-step-tabs button:not(:disabled) p::before {{ content: "✓";
  color: var(--fl-accent); flex-shrink: 0; }}
.st-key-idea-step-tabs button:disabled,
.st-key-idea-step-tabs button:disabled:is(:hover, :focus, :active) {{
  background: transparent; color: #8d8d8d; cursor: default; opacity: 1;
}}
.st-key-idea-step-tabs button[data-testid="stBaseButton-primary"]:disabled,
.st-key-idea-step-tabs button[data-testid="stBaseButton-primary"]:disabled:is(:hover, :focus, :active) {{
  background: var(--fl-accent); color: var(--fl-ink); opacity: 1;
}}
.st-key-idea-step-tabs button[data-testid="stBaseButton-primary"] p {{ font-weight: 600; }}
.st-key-idea-step-tabs button:not(:disabled):hover {{ background: #000000; color: white; }}
.fl-nav-balance {{ display: block; width: 84px; }}
.st-key-ideas .fl-eyebrow {{ display: none; }}
.st-key-idea-conditions .fl-chips {{ margin: 0; }}
.st-key-idea-conditions {{ margin: 14px 0 4px; }}
.st-key-idea-demo-notice details {{ background: var(--fl-surface-2);
  border: 0; border-radius: 8px; }}
.st-key-idea-demo-notice summary {{ padding: 10px 16px; color: var(--fl-ink-2); }}
.st-key-idea-demo-notice summary p {{ font-size: 11.7px; }}
.st-key-idea-demo-notice summary p::before {{ content: ""; display: inline-block;
  width: 6px; height: 6px; border-radius: 50%; background: var(--fl-accent);
  margin-right: 8px; vertical-align: middle; }}
.st-key-idea-demo-notice summary::after {{ content: "설명 보기"; margin-left: auto;
  font-size: 10.8px; color: var(--fl-ink-3); white-space: nowrap; }}
.st-key-idea-demo-notice details[open] summary::after {{ content: "설명 접기"; }}
.st-key-idea-cards [data-testid="stHorizontalBlock"] {{ align-items: stretch; }}
.st-key-idea-cards [data-testid="stColumn"] > [data-testid="stVerticalBlock"] {{ height: 100%; }}
.st-key-idea-cards [data-testid="stColumn"] > [data-testid="stVerticalBlock"]
  > [data-testid="stLayoutWrapper"] {{ flex: 1 1 auto; }}
.st-key-idea-cards [class*="st-key-card-idea-"] {{ height: 100%; border: 1px solid var(--fl-line); }}
/* Figma 02-2: 카드 윗줄 왼쪽 형식 칩, 오른쪽 픽셀 아이콘 */
.fl-idea-card-head {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; }}
.fl-idea-card-head .fl-format {{ margin: 0; }}
.fl-format-icon {{ display: block; width: 24px; height: 24git add app/style.py docs/submission/manual.md streamlit_app.py tests/test_app.py assets/icons/formatspx; flex: none; image-rendering: pixelated; }}
.st-key-idea-cards [class*="st-key-card-idea-"] > [data-testid="stElementContainer"]:last-child {{
  margin-top: auto; padding-top: 8px;
}}
@media (max-width: 900px) {{
  .fl-nav-balance {{ display: none; }}
}}
@media (max-width: 700px) {{
  .st-key-idea-cards [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap; }}
  .st-key-idea-cards [data-testid="stColumn"] {{ width: 100%; flex: 1 1 100%; min-width: 0; }}
  .st-key-idea-cards [class*="st-key-card-idea-"] {{ height: auto; }}
}}

/* 04 기획서: 문서와 승인 패널 */
.st-key-plan {{ container-type: inline-size; container-name: plan;
  background: radial-gradient(ellipse 420px 280px at 100% 0, #ffddd233, transparent 75%); }}
.st-key-plan-layout > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {{
  display: grid; grid-template-columns: minmax(0, 896fr) minmax(0, 320fr); gap: 32px; align-items: start;
}}
.st-key-plan-layout > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
  width: 100%; min-width: 0;
}}
.st-key-plan .st-key-doc {{ padding: 48px 56px; border-radius: 16px;
  box-shadow: 0 12px 32px rgba(18,18,18,.035); }}
.st-key-plan .st-key-card-rail {{ padding: 24px; border-radius: 24px; box-shadow: none; }}
.st-key-plan .st-key-plan-downloads {{ gap: 6px; }}
.fl-plan-download-title {{ font-size: 14.4px; font-weight: 600; line-height: 1.6; margin: 0; }}
.fl-plan-approve-divider {{ border: 0; border-top: 1px solid var(--fl-line); margin: 0; }}
.st-key-plan .st-key-card-rail .st-key-plan-downloads button {{ min-height: 40px; border-radius: 8px; padding: 8px;
  background: var(--fl-surface); color: var(--fl-ink); border: 1px solid var(--fl-line); }}
.st-key-plan .st-key-card-rail .st-key-plan-downloads button p {{ font-size: 12px; }}
.st-key-plan .st-key-card-rail .st-key-plan-downloads button:hover {{ background: var(--fl-surface-2); border-color: var(--fl-ink); }}
/* 문서 우측 상단의 Preview / Edit 전환 */
.st-key-plan .st-key-doc > [data-testid="stTabs"] {{ width: 100%; }}
.st-key-plan .st-key-doc [role="tablist"] {{ display: flex; width: 100%; justify-content: flex-end; gap: 4px; }}
.st-key-plan .st-key-doc [role="tab"] {{ font-size: 13px; padding: 8px 16px; }}
.st-key-plan .st-key-doc [role="tab"] p {{ font-size: 13px; }}
.st-key-plan .st-key-doc textarea {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px; line-height: 1.7; }}
.st-key-plan-md-preview [data-testid="stMarkdownContainer"] {{ font-size: 17px; overflow-wrap: anywhere; }}
.st-key-plan-md-preview h1 {{ font-size: 32px; }}
.st-key-plan-md-preview h2 {{ font-size: 24px; }}
.st-key-plan-md-preview h3 {{ font-size: 17px; }}
.st-key-plan-md-preview table {{ width: 100%; font-size: 15px; }}
.st-key-plan-md-preview p, .st-key-plan-md-preview li {{ font-size: 17px; }}

.st-key-plan .fl-eyebrow {{ font-size: 11px; }}
.st-key-plan .fl-h1 {{ font-size: 43.2px; }}
.st-key-plan .fl-desc {{ font-size: 15.3px; }}
.fl-plan-document .fl-tag {{ font-size: 12px; }}
.fl-plan-table .fl-tag {{ font-size: 15px; }}
.fl-plan-table.overview table {{ font-size: 15px; }}
.fl-plan-table.limitations table, .fl-plan-table.sources table {{ font-size: 13px; }}
.fl-plan-section[aria-labelledby="plan-section-15"] h3,
[aria-labelledby="plan-section-15"] .fl-plan-copy p {{ font-size: 15px; }}
.fl-plan-document {{ font-family: {_FONT}; color: var(--fl-ink); min-width: 0; }}
.fl-plan-document h1 {{ font-family: {_FONT}; font-size: 32px; line-height: 1.35;
  letter-spacing: -.04em; margin: 30px 0 18px; padding: 0; overflow-wrap: anywhere; }}
.fl-plan-version {{ display: inline-block; padding: 6px 14px; border-radius: 999px;
  background: var(--fl-accent-soft); font-size: 12px; line-height: 1.6; }}
.fl-plan-version.approved {{ background: var(--fl-pass-soft); color: var(--fl-pass); }}
.fl-plan-chips {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 34px; }}
.fl-plan-chips > span {{ border: 1px solid var(--fl-line); border-radius: 999px;
  padding: 6px 12px; font-size: 13px; line-height: 1.5; }}
.fl-plan-section {{ margin-top: 34px; }}
.fl-plan-section h2 {{ display: flex; align-items: center; flex-wrap: wrap; gap: 10px;
  font-family: {_FONT}; font-size: 24px; font-weight: 600; line-height: 1.4;
  letter-spacing: -.025em; margin: 0 0 16px; padding: 0; }}
.fl-plan-section h2 .fl-tag {{ margin: 0; white-space: nowrap; }}
.fl-plan-section h3 {{ font-family: {_FONT}; font-size: 17px; font-weight: 600;
  margin: 20px 0 12px; padding: 0; line-height: 1.5; }}
.fl-plan-copy p {{ font-size: 17px; line-height: 1.85; margin: 0 0 12px;
  overflow-wrap: anywhere; word-break: normal; }}
.fl-plan-copy p:last-child {{ margin-bottom: 0; }}
.fl-plan-copy li {{ font-size: inherit; line-height: 1.85; margin: 8px 0; }}
.fl-plan-copy {{ font-size: 17px; }}
.fl-plan-table {{ width: 100%; border: 1px solid var(--fl-line); border-radius: 16px;
  overflow: hidden; background: var(--fl-surface); }}
.fl-plan-table table {{ width: 100%; table-layout: fixed; border-collapse: collapse;
  font-family: {_FONT}; font-size: 15px; line-height: 1.6; margin: 0; }}
.fl-plan-table th {{ text-align: left; padding: 12px 14px; background: var(--fl-surface-2);
  color: var(--fl-ink); font-weight: 600; border: 0; }}
.fl-plan-table td {{ padding: 12px 14px; color: var(--fl-ink-2); vertical-align: top;
  border: 0; border-top: 1px solid var(--fl-line); overflow-wrap: anywhere; }}
.fl-plan-table th:first-child, .fl-plan-table td:first-child {{ width: 22%; }}
.fl-plan-table.budget th:first-child {{ width: 30%; }}
.fl-plan-table.budget th:nth-child(2) {{ width: 30%; }}
.fl-plan-table.checks th:first-child {{ width: 10%; }}
.fl-plan-table.checks th:nth-child(2) {{ width: 13%; }}
.fl-plan-table.sources th:first-child {{ width: 36%; }}
.fl-plan-table.sources th:nth-child(2) {{ width: 14%; }}
/* 참고 사례 설명과 표: 본문 간격을 유지하고 축제명에 충분한 폭을 준다. */
[aria-labelledby="plan-section-13"] .fl-plan-copy {{ margin-bottom: 16px; }}
.fl-plan-table.reference th:first-child, .fl-plan-table.reference td:first-child {{ width: 75%; }}
.fl-plan-timing {{ margin-top: 14px; padding: 16px 20px; border-radius: 16px;
  background: var(--fl-sea-soft); color: var(--fl-ink-2); }}
.fl-plan-timing b {{ font-size: 14px; color: var(--fl-sea); font-weight: 600; }}
.fl-plan-timing p {{ font-size: 13px; line-height: 1.8; margin: 8px 0 0; overflow-wrap: anywhere; }}
.fl-plan-kpi {{ padding: 18px; border-radius: 16px; background: var(--fl-surface-2); margin-top: 12px; }}
.fl-plan-kpi-head {{ display: flex; justify-content: space-between; gap: 16px; align-items: baseline; }}
.fl-plan-kpi-head h3 {{ margin: 0; font-size: 17px; }}
.fl-plan-kpi-head small {{ font-size: 13px; color: var(--fl-ink-3); }}
.fl-plan-formula {{ font-size: 15px; line-height: 1.7; color: var(--fl-ink-2); margin: 12px 0; }}
.fl-plan-kpi-values {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
.fl-plan-kpi-values > div {{ background: var(--fl-surface); border-radius: 10px; padding: 12px 14px; min-width: 0; }}
.fl-plan-kpi-label {{ display: flex; align-items: center; flex-wrap: wrap; gap: 6px;
  font-size: 13px; color: var(--fl-ink-3); }}
.fl-plan-kpi-label .fl-tag {{ margin: 0; }}
.fl-plan-kpi-values p {{ font-size: 13px; line-height: 1.7; margin: 8px 0 0; color: var(--fl-ink-2);
  overflow-wrap: anywhere; }}
.fl-plan-program {{ display: grid; grid-template-columns: minmax(110px, .8fr) 2.6fr auto;
  align-items: center; gap: 16px; padding: 14px 18px; background: var(--fl-surface-2);
  border-radius: 16px; margin-top: 12px; }}
.fl-plan-program b {{ font-size: 15px; line-height: 1.6; }}
.fl-plan-program p {{ font-size: 14px; line-height: 1.6; color: var(--fl-ink-2); margin: 0; }}
.fl-plan-program small {{ font-size: 12px; color: var(--fl-ink-3); }}
.fl-plan-schedule > div {{ display: flex; align-items: center; gap: 18px;
  border-top: 1px solid var(--fl-line); padding: 14px 0; }}
.fl-plan-schedule span {{ min-width: 62px; text-align: center; padding: 5px 10px;
  border-radius: 8px; background: var(--fl-surface-2); font-size: 15px; }}
.fl-plan-schedule span.event {{ background: var(--fl-accent-soft); }}
.fl-plan-schedule p {{ margin: 0; font-size: 15px; line-height: 1.5; }}
.fl-plan-risk-notes {{ margin-top: 16px; padding: 18px; border-radius: 16px;
  background: var(--fl-surface-2); color: var(--fl-ink-2); }}
.fl-plan-risk-notes b {{ font-size: 14px; color: var(--fl-ink); }}
.fl-plan-risk-notes ul, .fl-plan-assumptions {{ padding-left: 18px; margin: 10px 0 0; }}
.fl-plan-risk-notes li {{ font-size: 13px; line-height: 1.85; margin: 8px 0; }}
.fl-plan-assumptions li {{ font-size: 15px; line-height: 1.85; color: var(--fl-ink-2); margin: 12px 0; }}
.fl-plan-caption {{ font-size: 13px; line-height: 1.7; color: var(--fl-ink-3); margin: 12px 0 0; }}
.fl-plan-rail-head small {{ font-family: {_PIXEL}; font-size: 11px; letter-spacing: .16em;
  color: var(--fl-ink-2); }}
.fl-plan-rail-head h2 {{ font-family: {_FONT}; font-size: 18px; font-weight: 600; padding: 0;
  margin: 20px 0; line-height: 1.5; }}
.fl-plan-rail-head p {{ font-size: 13px; color: var(--fl-ink-2); line-height: 1.8; margin: 0 0 18px; }}
.fl-plan-rail-note {{ display: flex; align-items: center; gap: 12px; border-radius: 16px;
  padding: 16px; margin-top: 14px; }}
.fl-plan-rail-note.warning {{ background: var(--fl-warn-soft); }}
.fl-plan-rail-note.success {{ background: var(--fl-pass-soft); color: var(--fl-pass); }}
.fl-plan-rail-note p {{ font-size: 12px; line-height: 1.7; margin: 0; }}
.fl-plan-rail-note .fl-check-icon {{ flex: none; width: 20px; height: 20px; background: none; }}
.fl-plan-rail-note .fl-check-icon img {{ width: 18px; height: 18px; }}
.fl-plan-rail-note.success img {{ filter: brightness(0) saturate(100%) invert(48%) sepia(53%) saturate(868%) hue-rotate(96deg) brightness(92%) contrast(91%); }}
.st-key-plan .st-key-card-rail button {{ border-radius: 8px; min-height: 56px; margin-top: 0;
  font-family: {_FONT}; font-size: 15px; }}
.st-key-plan .st-key-card-rail button p {{ font-size: 15px; }}
[data-testid="stMainBlockContainer"]:has(.st-key-plan) [data-testid="stCaptionContainer"] p {{ font-size: 12px;
  color: var(--fl-ink-3); overflow-wrap: anywhere; line-height: 1.8; }}
@container plan (max-width: 900px) {{
  .st-key-plan-layout > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {{ grid-template-columns: minmax(0, 1fr); }}
  .st-key-plan-layout > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
    flex: 1 1 100%; width: 100%; min-width: 0;
  }}
  .st-key-plan .st-key-doc {{ padding: 28px 24px; }}
}}
@media (max-width: 600px) {{
  .fl-plan-kpi-values {{ grid-template-columns: 1fr; }}
  .fl-plan-program {{ grid-template-columns: 1fr; gap: 6px; }}
  .fl-plan-kpi-head {{ flex-wrap: wrap; gap: 4px; }}
  .fl-plan-section h2 {{ font-size: 19.8px; }}
  .fl-plan-table td, .fl-plan-table th {{ padding: 10px 8px; }}
}}

/* 아이디어 요약 목록과 오른쪽 상세 패널 */
.fl-idea-summary {{ display: grid; gap: 18px; padding: 20px 0; margin-top: 12px;
  border-top: 1px solid var(--fl-line); }}
.fl-idea-summary-row {{ display: grid; grid-template-columns: 74px 1fr; gap: 10px; }}
.fl-idea-summary-label {{ font-size: 10.8px; color: var(--fl-ink-3); padding-top: 3px; }}
.fl-idea-summary-row b {{ display: block; font-size: 12.6px; line-height: 1.6;
  font-weight: 600; margin-top: 4px; word-break: keep-all; }}
[class*="st-key-card-idea-"] h3 {{ font-size: 19.8px; line-height: 1.4; }}
[class*="st-key-detail_"] button {{ width: 100%; background: var(--fl-ink);
  color: white; border-color: var(--fl-ink); }}
[class*="st-key-detail_"] button:hover {{ background: #2b2b2b; color: white; border-color: #2b2b2b; }}
[role="dialog"]:has(.fl-idea-detail) {{ position: fixed; inset: 0 0 0 auto;
  margin: 0; width: min(640px, 100vw); max-width: 100vw; height: 100dvh;
  max-height: 100dvh; overflow-y: auto; transform: none; border: 0; border-radius: 28px 0 0 28px;
  background: var(--fl-surface); box-shadow: -16px 0 64px rgba(18, 18, 18, .14); }}
[role="dialog"]:has(.fl-idea-detail) [data-testid="stDialogContent"] {{
  max-height: calc(100dvh - 80px); overflow-y: auto; padding-bottom: 12px; }}
[role="dialog"]:has(.fl-idea-detail) h3 {{ font-size: 25.2px; word-break: keep-all; }}
[class*="st-key-pick_"] button {{ background: var(--fl-accent); color: #fff;
  border-color: var(--fl-accent); }}
[class*="st-key-pick_"] button:hover {{ background: #ff7a22; color: #fff;
  border-color: #ff7a22; }}
.st-key-idea-detail-actions {{ position: sticky; bottom: -1px; background: var(--fl-surface);
  border-top: 1px solid var(--fl-line); padding-top: 16px; padding-bottom: 8px; z-index: 2; }}
[role="dialog"]:has(.fl-idea-detail) {{ padding: 32px 40px; }}
[role="dialog"]:has(.fl-idea-detail) h2 {{ display: none; }}
.fl-idea-detail {{ font-family: {_FONT}; color: var(--fl-ink); }}
.fl-idea-detail h1 {{ font-size: 25.2px; line-height: 1.35; letter-spacing: -.04em;
  margin: 26px 0 12px; padding: 0; word-break: keep-all; }}
.fl-detail-concept {{ font-size: 14.4px; line-height: 1.7; color: var(--fl-ink-2); margin: 0; }}
.fl-detail-section {{ margin-top: 28px; }}
[role="dialog"] .fl-detail-section h3 {{ display: flex; align-items: center; flex-wrap: wrap;
  gap: 10px; font-size: 15.3px; line-height: 1.5; margin: 0 0 16px; padding: 0; }}
.fl-detail-section h3 .fl-tag {{ margin: 0; }}
.fl-detail-copy {{ font-size: 12.6px; line-height: 1.85; margin: 0; word-break: keep-all; }}
.fl-detail-metrics {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }}
.fl-detail-metrics > div {{ background: var(--fl-surface-2); border-radius: 18px; padding: 18px 16px; }}
.fl-detail-metrics strong {{ display: block; font-size: 30.6px; line-height: 1.25;
  letter-spacing: -.04em; font-weight: 700; }}
.fl-detail-metrics small {{ display: block; color: var(--fl-ink-2); font-size: 9.9px;
  line-height: 1.5; margin-top: 6px; word-break: keep-all; }}
.fl-detail-note {{ color: var(--fl-ink-3); font-size: 9.9px; line-height: 1.6; margin: 10px 0 0; }}
.fl-detail-row {{ display: flex; align-items: baseline; justify-content: space-between;
  gap: 20px; font-size: 12.6px; line-height: 1.7; padding: 8px 0; }}
.fl-detail-row span {{ color: var(--fl-ink-2); word-break: keep-all; }}
.fl-detail-row b {{ font-weight: 600; text-align: right; flex-shrink: 0; }}
.fl-detail-budget {{ display: grid; gap: 16px; margin-bottom: 16px; }}
.fl-budget-row {{ display: grid; grid-template-columns: 96px minmax(30px, 1fr) 88px;
  gap: 12px; align-items: center; font-size: 10.8px; }}
.fl-budget-row > span {{ color: var(--fl-ink-2); }}
.fl-budget-row > b {{ font-weight: 500; }}
.fl-budget-track {{ height: 14px; }}
.fl-budget-track i {{ display: block; height: 100%; border-radius: 999px; }}
.fl-budget-track .input {{ background: var(--fl-accent); }}
.fl-budget-track .median {{ background: var(--fl-line); }}
.fl-detail-interest {{ display: flex; align-items: baseline; flex-wrap: wrap; gap: 10px;
  font-size: 11.7px; line-height: 1.8; color: var(--fl-ink-2); }}
.fl-detail-disclaimer {{ display: flex; align-items: baseline; gap: 10px; margin-top: 26px;
  padding: 18px; background: var(--fl-pending-soft); border-radius: 18px;
  font-size: 10.8px; color: var(--fl-ink-2); line-height: 1.8; }}
.fl-detail-disclaimer .fl-tag {{ flex-shrink: 0; }}
@media (max-width: 480px) {{
  [role="dialog"]:has(.fl-idea-detail) {{ padding: 24px 20px; }}
  .fl-detail-metrics {{ gap: 8px; }}
  .fl-detail-metrics > div {{ padding: 14px 10px; }}
  .fl-detail-metrics strong {{ font-size: 25.2px; }}
  .fl-budget-row {{ grid-template-columns: 76px minmax(20px, 1fr) 70px; gap: 8px; }}
}}
@media (max-width: 640px) {{
  [role="dialog"]:has(.fl-idea-detail) {{ border-radius: 0; }}
}}
/* 03·04 개정안: 한 화면에서 확인 → 수정 → 재확인 */
[data-testid="stMainBlockContainer"]:has(.st-key-verification) {{
  max-width: 1184px;
}}
.st-key-verification {{ gap: 28px; }}
.st-key-verification .fl-head {{ margin: 0; }}
.st-key-verification .fl-h1 {{ font-size: 43.2px; }}
.st-key-verification .fl-desc {{ font-size: 15.3px; max-width: none; line-height: 1.6; }}
.fl-check-selection {{ position: relative; overflow: hidden; background: var(--fl-surface);
  border-radius: 24px; padding: 24px 28px 24px 32px; display: flex; flex-direction: column; gap: 8px; }}
.fl-check-selection::before {{ content: ""; position: absolute; inset: 0 auto 0 0; width: 6px;
  background: var(--fl-accent); }}
.fl-check-selection-label {{ font-size: 11.7px; font-weight: 600; color: #c4561a; }}
.fl-check-selection-body {{ display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }}
.fl-check-selection h2 {{ margin: 0; padding: 0; font-size: 23.4px; font-weight: 700;
  letter-spacing: -.03em; line-height: 1.3; }}
.fl-check-selection .fl-format {{ margin: 0; }}
.fl-check-selection p {{ margin: 0; font-size: 13.5px; line-height: 1.6; color: var(--fl-ink-2); }}
.fl-plan-strip {{ display: grid; grid-template-columns: 1.1fr 1fr 1.4fr .8fr; align-items: stretch;
  background: var(--fl-surface); border: 1px solid var(--fl-line); border-radius: 20px; overflow: hidden; }}
.fl-plan-strip > div {{ display: flex; flex-direction: column; justify-content: center; gap: 6px;
  padding: 16px 24px; min-width: 0; }}
.fl-plan-strip > div + div {{ border-left: 1px solid var(--fl-line); }}
.fl-plan-strip small {{ font-size: 10.8px; color: var(--fl-ink-3); }}
.fl-plan-strip b {{ font-size: 15.3px; font-weight: 600; overflow-wrap: anywhere; }}
.fl-plan-strip-name {{ background: var(--fl-surface-2); }}
.fl-plan-strip-name .fl-badge {{ align-self: flex-start; }}
@media (max-width: 700px) {{
  .fl-check-selection {{ padding: 20px 20px 20px 26px; }}
  .fl-check-selection h2 {{ font-size: 19.8px; }}
  .fl-plan-strip {{ grid-template-columns: 1fr 1fr; }}
  .fl-plan-strip > div + div {{ border-left: none; }}
  .fl-plan-strip > div {{ border-top: 1px solid var(--fl-line); }}
  .fl-plan-strip > div:nth-child(-n+2) {{ border-top: none; }}
  .fl-plan-strip > div:nth-child(even) {{ border-left: 1px solid var(--fl-line); }}
}}
.st-key-verification [data-testid="stCaptionContainer"] p {{ color: var(--fl-ink-2); font-size: 12.6px; line-height: 1.6; }}
.st-key-verification h3 {{ font-size: 21.6px; padding: 0; line-height: 1.5; }}
.st-key-verification [data-testid="stColumn"] > [data-testid="stVerticalBlock"] {{ gap: 16px; }}
.st-key-verification [class*="st-key-res-"] {{
  border: none; box-shadow: none; padding: 24px; gap: 16px;
}}
.st-key-verification [class*="st-key-res-"] p {{
  font-size: 12.6px; line-height: 1.6; overflow-wrap: anywhere;
}}
.st-key-verification .fl-check-head {{ gap: 12px; align-items: center; margin: 0; }}
.st-key-verification .fl-check-head > span {{ display: flex; gap: 6px; flex-wrap: wrap; }}
.st-key-verification .fl-check-head b {{ font-size: 16.2px; font-weight: 600; }}
.st-key-verification [class*="st-key-check-numbers-"] {{ gap: 6px; }}
.st-key-verification [class*="st-key-check-numbers-"] p {{
  font-size: 10.8px; line-height: 1.5; color: var(--fl-ink-2);
}}
.st-key-verification [class*="st-key-check-source-"] p {{
  font-size: 9px; line-height: 1.6; color: var(--fl-ink-3);
}}
.st-key-verification [class*="st-key-res-"] [data-testid="stExpander"] details {{
  border: none; border-radius: 0; background: transparent;
}}
.st-key-verification [class*="st-key-res-"] [data-testid="stExpander"] summary {{
  padding: 8px 0 0; color: var(--fl-ink-2);
}}
.st-key-verification [class*="st-key-res-"] [data-testid="stExpander"] summary p {{
  font-size: 10.8px;
}}
.st-key-verification [class*="st-key-chg-"] {{
  border: none; border-radius: 16px; background: var(--fl-sea-soft);
  box-shadow: none; padding: 16px; gap: 6px;
}}
.st-key-verification [class*="st-key-chg-"] p {{
  color: var(--fl-sea); font-size: 12.6px; line-height: 1.6;
}}
.st-key-verification [class*="st-key-chg-"] [data-testid="stCaptionContainer"] p {{
  font-size: 10.8px;
}}
.st-key-verification [data-testid="stTabs"] [data-baseweb="tab-list"] {{
  gap: 16px; background: transparent; margin-bottom: 28px;
}}
.st-key-verification [data-testid="stTabs"] [data-baseweb="tab"] {{
  border: 1px solid var(--fl-ink); background: transparent; border-radius: 8px;
  padding: 10px 20px; height: auto; color: var(--fl-ink);
}}
.st-key-verification [data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] {{
  background: var(--fl-accent); border-color: var(--fl-accent);
}}
.st-key-verification [data-baseweb="tab-highlight"],
.st-key-verification [data-baseweb="tab-border"] {{ display: none; }}
/* 추천안·고친 안: 상단 단계 탭과 같은 검은 캡슐 (Streamlit 1.5x react-aria 탭) */
.st-key-verification [data-testid="stTabs"] [role="tablist"] {{
  display: inline-flex; width: fit-content; max-width: 100%; align-self: flex-start;
  gap: 4px; padding: 6px; margin-bottom: 20px;
  background: var(--fl-ink); border-radius: 999px; border: none; box-shadow: none;
}}
.st-key-verification [data-testid="stTabs"] [role="tablist"]::after,
.st-key-verification [data-testid="stTabs"] [role="tablist"]::before {{ display: none; }}
.st-key-verification [data-testid="stTab"] {{
  padding: 10px 22px; border-radius: 999px; border: none; background: transparent;
  color: rgba(255, 255, 255, .6); cursor: pointer; transition: background .15s, color .15s;
}}
.st-key-verification [data-testid="stTab"] p {{
  font-size: 13.5px; font-weight: 500; color: inherit; margin: 0;
}}
.st-key-verification [data-testid="stTab"]:hover {{ color: #fff; }}
.st-key-verification [data-testid="stTab"][data-selected="true"] {{
  background: var(--fl-accent); color: var(--fl-ink);
}}
.st-key-verification [data-testid="stTab"][data-selected="true"] p {{ font-weight: 700; }}
.st-key-verification [data-testid="stTabs"] .react-aria-SelectionIndicator {{ display: none; }}
.st-key-verification [data-testid="stTabPanel"] {{ padding-top: 0; }}
.st-key-verification [data-testid="stForm"] {{ border: none; padding: 0; }}
.st-key-verification [class*="st-key-check-field-"] {{
  border: 1px solid var(--fl-line); border-radius: 16px;
  background: var(--fl-surface); padding: 18px 20px; min-height: 108px;
}}
.st-key-verification [class*="st-key-check-field-"] [data-testid="stWidgetLabel"] p {{
  font-size: 10.8px; color: var(--fl-ink-3);
}}
.st-key-verification [class*="st-key-check-field-"] [data-baseweb="select"] > div {{
  border: none; background: transparent; padding-left: 0;
}}
.st-key-verification [class*="st-key-check-field-"] [data-baseweb="select"] {{
  font-size: 16.2px; font-weight: 600;
}}
.st-key-verification [data-testid="stFormSubmitButton"] button {{
  background: transparent; border: 1px solid var(--fl-ink); color: var(--fl-ink);
}}
.st-key-verification button[data-testid^="stBaseButton"] {{
  border-radius: 8px; min-height: 40px; font-size: 11.7px; font-weight: 400;
}}
.st-key-verification .st-key-check-proceed button {{
  background: var(--fl-accent); border-color: var(--fl-accent); color: var(--fl-ink);
}}
.st-key-verification .st-key-check-proceed button:disabled {{ opacity: .35; }}
.st-key-verification [data-testid="stSpinner"] {{
  padding: 16px; border-radius: 16px; background: var(--fl-sea-soft); color: var(--fl-sea);
}}
.st-key-verification [data-testid="stAlert"] {{ font-size: 12.6px; }}
/* 확인 과정과 바뀐 점: 회차 줄 → 바꾼 점 상자 → 다음 회차 줄 (세로 타임라인) */
.st-key-verification [class*="st-key-timeline-"] {{
  position: relative; gap: 14px; padding: 24px 28px; background: var(--fl-surface);
  border-radius: 24px;
}}
.st-key-verification [class*="st-key-timeline-"]::before {{
  content: ""; position: absolute; left: 33px; top: 40px; bottom: 40px; width: 2px;
  background: var(--fl-line);
}}
.fl-round {{ position: relative; display: flex; align-items: center; flex-wrap: wrap;
  gap: 8px 12px; padding-left: 28px; }}
.fl-round-dot {{ position: absolute; left: 0; top: 50%; width: 12px; height: 12px; margin-top: -6px;
  border-radius: 50%; background: var(--fl-surface); border: 2px solid var(--fl-ink-3); }}
.fl-round.last .fl-round-dot {{ background: var(--fl-accent); border-color: var(--fl-accent); }}
.fl-round > b {{ font-size: 13.5px; font-weight: 700; white-space: nowrap; }}
.fl-round-now {{ font-size: 9.9px; font-weight: 600; color: #c4561a; background: var(--fl-accent-soft);
  padding: 2px 8px; border-radius: 999px; }}
.fl-round-items {{ display: flex; flex-wrap: wrap; gap: 6px 14px; margin-left: auto; }}
.fl-round-item {{ display: inline-flex; align-items: center; gap: 6px; font-size: 11.7px;
  color: var(--fl-ink-2); }}
.st-key-verification [class*="st-key-timeline-"] [class*="st-key-chg-"] {{ margin-left: 28px; }}
.st-key-verification [class*="st-key-timeline-"] [data-testid="stMarkdownContainer"] {{ margin: 0; }}
.st-key-verification [class*="st-key-timeline-"] [class*="st-key-chg-"] [data-testid="stMarkdownContainer"] p {{
  margin: 0;
}}
@media (max-width: 700px) {{
  .st-key-verification [class*="st-key-timeline-"] {{ padding: 20px 18px; }}
  .st-key-verification [class*="st-key-timeline-"]::before {{ left: 23px; }}
  .fl-round-items {{ margin-left: 0; }}
  .st-key-verification [class*="st-key-timeline-"] [class*="st-key-chg-"] {{ margin-left: 20px; }}
}}
/* 직접 고쳐서 다시 확인: 제목 아래 안내 두 줄 */
.st-key-verification .st-key-check-manual-intro {{ gap: 2px; margin-top: -2px; }}
.st-key-check-manual-intro [data-testid="stCaptionContainer"],
.st-key-verification .st-key-check-manual-intro [data-testid="stCaptionContainer"] p {{ margin: 0; }}
/* 진행 막힘: 실패 이유·근거·수정 방법을 한 카드에 */
.st-key-verification .st-key-check-blocked {{
  position: relative; overflow: hidden; gap: 8px; padding: 24px 28px 24px 34px;
  background: var(--fl-surface); border: 1px solid var(--fl-fail-soft); border-radius: 24px;
}}
.st-key-verification .st-key-check-blocked::before {{
  content: ""; position: absolute; inset: 0 auto 0 0; width: 6px; background: var(--fl-fail);
}}
.st-key-check-blocked [data-testid="stAlert"] {{ margin-bottom: 8px; }}
.st-key-check-blocked [data-testid="stAlertContainer"] {{
  background: var(--fl-fail-soft); color: var(--fl-fail); border-radius: 12px; padding: 12px 16px;
}}
.st-key-check-blocked [data-testid="stAlertContent"] p {{
  color: var(--fl-fail); font-size: 13.5px; font-weight: 600;
}}
/* Streamlit 기본값(margin-bottom: -16px) 때문에 상자 높이가 글자보다 작아지는 것을 막는다 */
.st-key-check-blocked [data-testid="stMarkdownContainer"],
.st-key-check-blocked [data-testid="stCaptionContainer"] {{ margin: 0; }}
.st-key-check-blocked [data-testid="stMarkdownContainer"] p {{
  margin: 0; font-size: 12.6px; line-height: 1.7; color: var(--fl-ink-2);
}}
.st-key-check-blocked [data-testid="stMarkdownContainer"] p strong {{ color: var(--fl-ink); }}
.st-key-verification [class*="st-key-check-blocked-fix-"] {{
  padding: 14px 16px; border-radius: 12px; background: var(--fl-accent-soft); margin: 6px 0 4px;
}}
.st-key-verification [class*="st-key-check-blocked-fix-"] [data-testid="stMarkdownContainer"] p {{
  color: var(--fl-ink);
}}
.st-key-verification [class*="st-key-check-blocked-fix-"] [data-testid="stMarkdownContainer"] p strong {{
  color: #c4561a;
}}
.st-key-check-blocked [data-testid="stCaptionContainer"] p {{
  font-size: 10.8px; color: var(--fl-ink-3); padding-top: 8px; border-top: 1px solid var(--fl-line);
}}
@media (max-width: 700px) {{
  .st-key-verification .st-key-check-blocked {{ padding: 20px 18px 20px 24px; }}
}}
.st-key-verification [class*="st-key-check-field-"] .react-aria-ComboBox > div {{ background: transparent; border-color: transparent; }}

@media (max-width: 700px) {{
  .st-key-verification .fl-h1 {{ font-size: 28.8px; }}
  .st-key-verification .fl-desc {{ font-size: 13.5px; }}
  .st-key-verification {{ gap: 20px; }}
  .st-key-verification [data-testid="stTabs"] [data-baseweb="tab-list"] {{ gap: 8px; }}
  .st-key-verification [data-testid="stTabs"] [data-baseweb="tab"] {{ padding: 10px 14px; }}
}}

/* Figma 03: 시기·장소 2열, 대상·위험·규모 3열 */
[data-testid="stMainBlockContainer"]:has(.st-key-verification) {{ max-width: 1312px; }}
.st-key-verification .fl-h1 {{ font-size: 39.6px; }}
.st-key-verification [class*="st-key-check-row-"] [data-testid="stHorizontalBlock"] {{
  align-items: stretch;
}}
.st-key-verification [class*="st-key-check-row-"] [data-testid="stColumn"] > [data-testid="stVerticalBlock"] {{
  height: 100%;
}}
.st-key-verification [class*="st-key-res-"] {{ height: 100%; gap: 16px; }}
.fl-check-title {{ display: flex; gap: 12px; align-items: center; flex: 1; min-width: 0; }}
.fl-check-icon {{ display: inline-flex; align-items: center; justify-content: center;
  width: 40px; height: 40px; flex-shrink: 0; border-radius: 8px; background: var(--fl-surface-2); }}
.fl-check-icon img {{ display: block; }}
.fl-check-metric {{ display: flex; align-items: center; gap: 12px; padding: 16px;
  background: var(--fl-surface-2); border-radius: 16px; min-height: 72px; }}
.fl-check-metric strong {{ font-size: 25.2px; font-weight: 700; line-height: 1.25; white-space: nowrap;
  letter-spacing: -.03em; }}
.fl-check-metric > div {{ display: flex; flex-direction: column; gap: 4px; min-width: 0; }}
.fl-check-metric > div > span:last-child {{ color: var(--fl-ink-2); font-size: 10.8px; line-height: 1.5; }}
.fl-check-metric .fl-tag {{ align-self: flex-start; }}
.fl-check-warning {{ background: var(--fl-warn-soft); padding: 12px; border-radius: 8px; }}
.fl-check-warning-title {{ display: flex; gap: 6px; align-items: center;
  font-size: 10.8px; font-weight: 500; color: var(--fl-warn); margin-bottom: 8px; }}
.fl-check-warning-title .fl-check-icon {{ width: 14px; height: 14px; background: transparent; }}
.st-key-verification [class*="st-key-res-"] .fl-check-warning p {{
  margin: 0; font-size: 10.8px; line-height: 1.6; color: var(--fl-ink-2);
}}
.st-key-verification [class*="st-key-res-"] [data-testid="stExpander"] {{ margin-top: auto; }}
.st-key-verification [class*="st-key-res-"] [data-testid="stExpander"] [data-testid="stCaptionContainer"] p {{
  font-size: 10.8px;
}}
@media (max-width: 700px) {{
  .st-key-verification .fl-h1 {{ font-size: 28.8px; }}
  .fl-check-metric strong {{ font-size: 21.6px; }}
  .st-key-verification [class*="st-key-res-"] {{ height: auto; }}
}}


.st-key-verification {{ container-type: inline-size; container-name: verification; }}
@container verification (max-width: 900px) {{
  .st-key-verification [class*="st-key-check-row-"] [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap; }}
  .st-key-verification [class*="st-key-check-row-"] [data-testid="stColumn"] {{
    width: 100% !important; flex: 1 1 100% !important; min-width: 0 !important;
  }}
}}
.fl-check-title b {{ white-space: nowrap; }}

/* Figma 05: 홍보물 */
[data-testid="stMainBlockContainer"]:has(.st-key-promo) {{ max-width: 1312px; }}
.st-key-promo {{ gap: 24px; }}
.st-key-promo [data-testid="stColumn"] > [data-testid="stVerticalBlock"] {{ gap: 16px; }}
/* 노란 안내 띠: st.warning을 ⚠ 픽셀 아이콘 + 연노랑 띠로 */
.st-key-promo [class*="st-key-promo-notice-"] [data-testid="stAlertContainer"] {{
  background: var(--fl-warn-soft); border-radius: 16px; padding: 16px 24px; color: var(--fl-ink);
}}
.st-key-promo [class*="st-key-promo-notice-"] [data-testid="stAlertContent"] {{
  display: flex; align-items: center; gap: 12px;
}}
.st-key-promo [class*="st-key-promo-notice-"] [data-testid="stAlertContent"]::before {{
  content: ""; flex: none; width: 20px; height: 20px; background: url("{_icon_uri("warning")}") center / contain no-repeat;
}}
.st-key-promo [class*="st-key-promo-notice-"] [data-testid="stAlertContent"] p {{
  font-size: 13.5px; line-height: 1.5; color: var(--fl-ink); margin: 0;
}}
.st-key-promo .st-key-promo-notice-synthetic {{ max-width: 960px; }}
.st-key-promo .st-key-card-poster {{ padding: 0; overflow: hidden; border: none; border-radius: 4px;
  box-shadow: 0 24px 48px rgba(18, 18, 18, .10); }}
.st-key-promo .st-key-card-poster img {{ display: block; width: 100%; height: auto; }}
.st-key-promo [data-testid="stCaptionContainer"] p {{ font-size: 11.7px; color: var(--fl-ink-3); }}
.st-key-promo .st-key-poster-download button,
.st-key-promo .st-key-promo-zip button {{
  border-radius: 8px; background: var(--fl-surface); border: 1.5px solid var(--fl-ink); color: var(--fl-ink);
}}
.st-key-promo .st-key-poster-download button {{ min-height: 48px; padding: 0 24px; }}
.st-key-promo .st-key-card-sns,
.st-key-promo .st-key-card-checks {{ padding: 28px 32px; gap: 16px; }}
.fl-card-head {{ display: flex; align-items: center; justify-content: space-between; gap: 12px;
  flex-wrap: wrap; }}
.fl-card-head b {{ font-size: 18px; font-weight: 600; }}
.fl-card-head small {{ font-size: 10.8px; color: var(--fl-ink-3); }}
.fl-card-head .fl-check-icon {{ background: transparent; width: 28px; height: 28px; }}
.fl-count {{ font-size: 11.7px; padding: 4px 16px; border: 1px solid var(--fl-line); border-radius: 999px; }}
.fl-sns-body {{ white-space: pre-wrap; background: var(--fl-surface-2); border-radius: 16px;
  padding: 20px 24px; font-size: 13.5px; line-height: 1.75; color: var(--fl-ink); overflow-wrap: anywhere; }}
.st-key-card-sns iframe {{ display: block; }}
.fl-promo-checks {{ list-style: none; margin: 4px 0 0; padding: 0; display: flex; flex-direction: column;
  gap: 10px; font-size: 12.6px; line-height: 1.6; }}
.fl-promo-checks li {{ display: flex; gap: 4px; }}
.fl-promo-note {{ margin: 8px 0 0; font-size: 10.8px; color: var(--fl-ink-3); line-height: 1.6; }}
.st-key-promo .st-key-promo-save button,
.st-key-promo .st-key-promo-zip button {{ min-height: 64px; border-radius: 8px; font-size: 14.4px; }}
.fl-promo-files {{ display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }}
.fl-promo-files small {{ font-size: 10.8px; color: var(--fl-ink-3); margin-right: 4px; }}
.fl-promo-files span {{ font-size: 11.7px; padding: 8px 16px; background: var(--fl-surface);
  border: 1px solid var(--fl-line); border-radius: 999px; }}
.fl-promo-info {{ display: flex; align-items: center; gap: 16px; padding: 20px 24px;
  background: var(--fl-sea-soft); border-radius: 16px; font-size: 13.5px; line-height: 1.7; color: var(--fl-ink); }}
.fl-promo-info .fl-check-icon {{ background: transparent; width: 20px; height: 20px; }}
@media (max-width: 700px) {{
  .st-key-promo .st-key-card-sns, .st-key-promo .st-key-card-checks {{ padding: 20px; }}
  .fl-notice, .fl-promo-info {{ padding: 14px 16px; font-size: 12.6px; }}
}}

</style>
"""


def logo_html() -> str:
    return (
        f'<div class="fl-logo"><img class="fl-blob" src="{_BRAND_MARK_URI}" alt="">'
        '<div><b>제주 축제 메이커</b><small>JEJU FESTIVAL MAKER</small></div></div>'
    )


def nav_html(step: int) -> str:
    """로고 + 단계 캡슐 탭 (보여주기만, 누르는 기능 없음)."""
    tabs = []
    for i, name in enumerate(screen.STEPS, start=1):
        cls = "active" if i == step else "done" if i < step else ""
        tabs.append(f'<span class="fl-tab {cls}">{i:02d} {escape(name)}</span>')
    return (
        f'<div class="fl-nav">{logo_html()}'
        f'<div class="fl-steps">{"".join(tabs)}</div></div>'
    )


def idea_detail_html(card) -> str:
    """상세 근거를 숫자 카드, 현황 행, 예산 비교로 구성한다."""
    def section(title, body, kind=None):
        badge = tag_html(kind) if kind else ""
        return (
            f'<section class="fl-detail-section"><h3>{escape(title)}{badge}</h3>'
            f"{body}</section>"
        )

    def row(label, value):
        return (
            f'<div class="fl-detail-row"><span>{escape(label)}</span>'
            f'<b>{escape(value)}</b></div>'
        )

    trend = card.evidence.trend
    ready = trend.status != "pending"
    verdict = trend.verdict if ready else None
    short_verdict = next(
        (v for k, v in (("확실한 상승", "상승"), ("관찰 대상", "관찰"),
                        ("성숙·감소", "감소"), ("정체", "정체"))
         if verdict and verdict.startswith(k)),
        "확인 중",
    )
    metrics = (
        (f"{trend.new_count}개" if ready and trend.new_count is not None else "—",
         "2023년 이후 신설"),
        (f"{trend.new_lift:.1f}배" if ready and trend.new_lift is not None else "—",
         "신설 비율"),
        (short_verdict, f"판정: {verdict}" if verdict else "데이터 대기"),
    )
    tiles = '<div class="fl-detail-metrics">' + "".join(
        f'<div><strong>{escape(value)}</strong><small>{escape(label)}</small></div>'
        for value, label in metrics
    ) + "</div>"
    tiles += '<p class="fl-detail-note">신설 비율은 기존 축제 대비 새 축제의 형식 비율이에요.</p>'
    gap = card.evidence.jeju_gap
    jeju = row(
        f"같은 형식({card.format}) 축제",
        f"{gap.jeju_count}개" if gap.status != "pending" and gap.jeju_count is not None
        else "확인 중",
    )
    for festival in card.existing_jeju_festivals:
        jeju += row("비슷한 소재: " + festival.name,
                    f"{festival.month}월" if festival.month is not None else "개최 월 미확인")
    months = screen.months_text(card.timing.recommended_months)
    count = card.timing.jeju_festivals_in_month
    jeju += row(f"{months}에 열리는 제주 축제", f"{count}개" if count is not None else "확인 중")
    budget = card.budget
    maximum = max(budget.input_krw or 0, budget.format_median_krw or 0, 1)
    bars = '<div class="fl-detail-budget">'
    for label, value, cls in (("입력한 예산", budget.input_krw, "input"),
                              ("같은 형식 중앙값", budget.format_median_krw, "median")):
        percent = (value or 0) / maximum * 100
        bars += (
            f'<div class="fl-budget-row"><span>{label}</span>'
            f'<div class="fl-budget-track"><i class="{cls}" style="width:{percent:.2f}%"></i></div>'
            f'<b>{escape(screen.won(value))}</b></div>'
        )
    bars += "</div>"
    if budget.format_median_krw is None:
        explanation = "비교할 예산은 아직 확인 중이에요."
    elif budget.scale == "소규모 버전":
        explanation = "→ 소규모 버전으로 제안해요."
    elif budget.input_krw is None:
        explanation = "예산을 정하면 규모를 맞춰 드릴게요."
    else:
        explanation = "→ 입력한 예산으로 기본 규모를 제안해요."
    if budget.small_examples:
        explanation += " 비슷한 소규모 사례: " + ", ".join(
            f"{e.name} ({screen.won(e.budget_krw)})" for e in budget.small_examples
        )
    bars += f'<p class="fl-detail-copy">{escape(explanation)}</p>'
    vi = card.evidence.visitor_interest
    _, interest, _ = screen.evidence_lines(card)[2]
    if vi.status == "pending" or vi.value is None:
        interest = "이 소재의 관광객 관심 지표는 아직 확인 중이에요."
        interest = tag_html("데이터 대기") + f"<span>{escape(interest)}</span>"
    else:
        interest = f"<span>{escape(interest)}</span>"
    parts = [
        '<div class="fl-idea-detail">',
        format_html(f"{card.format} × {card.material}"),
        f'<h1>{escape(card.title)}</h1><p class="fl-detail-concept">{escape(card.concept)}</p>',
    ]
    reason = card.pick_reason or trend.interpretation
    if reason:
        parts.append(section("왜 이 아이디어인가요?",
                             f'<p class="fl-detail-copy">{escape(reason)}</p>', "에이전트 해석"))
    parts.append(section("전국 트렌드", tiles, "사실" if ready else "데이터 대기"))
    parts.append(section("제주 현황", jeju,
                         "사실" if gap.status != "pending" else "데이터 대기"))
    if card.reference.designated_festivals:
        examples = "".join(row(f.name, f.grade) for f in card.reference.designated_festivals)
        parts.append(section("비슷한 성공 축제", examples, "사실"))
    parts.append(section("예산", bars, "에이전트 해석"))
    parts.append(section("관광객 관심", f'<div class="fl-detail-interest">{interest}</div>'))
    parts.append(
        '<div class="fl-detail-disclaimer">' + tag_html("참고 수치")
        + '<span>축제별 집계 방식이 달라 단순 비교에 주의가 필요한 값이에요.</span></div>'
    )
    parts.append("</div>")
    return "".join(parts)


def evidence_legend_html() -> str:
    """하단에서 근거 배지의 의미를 한 번에 안내한다."""
    entries = (
        ("데이터", "출처 자료에서 확인한 값이에요."),
        ("에이전트 해석", "데이터를 바탕으로 에이전트가 분석하고 제안한 내용이에요."),
        ("참고 수치", "축제별 집계 방식이 달라 단순 비교에 주의가 필요한 값이에요."),
    )
    return '<div class="fl-evidence-legend" role="note" aria-label="근거 표시 안내">' + "".join(
        f"<span>{tag_html(kind)}<span>{escape(description)}</span></span>"
        for kind, description in entries
    ) + "</div>"


def idea_summary_html(rows: list[tuple[str, str, str]]) -> str:
    """짧은 요약에서도 사실과 해석의 구분은 유지한다."""
    return '<div class="fl-idea-summary">' + "".join(
        '<div class="fl-idea-summary-row">'
        f'<span class="fl-idea-summary-label">{escape(label)}</span>'
        f'<div>{tag_html(kind)}<b>{escape(value)}</b></div></div>'
        for label, value, kind in rows
    ) + "</div>"


def sidebar_html(has_llm: bool) -> str:
    """AI 설정 상태와 서비스 이용 순서를 보여주는 설정 패널."""
    state = "사용 가능" if has_llm else "설정 필요"
    title = "함께 기획할 준비가 됐어요" if has_llm else "예시 카드로 먼저 둘러보세요"
    description = (
        "문장으로 조건을 정리하고, 아이디어와 기획서 문장을 만드는 데 AI를 사용합니다."
        if has_llm
        else "AI 설정이 없으면 한 문장 입력·새 카드·기획서는 안내 문구로 대신해요. "
        "예시 카드로 흐름을 볼 수 있어요."
    )
    guide = ("원하는 축제를 적어주세요", "아이디어를 골라주세요", "제주 데이터로 확인할 수 있어요", "기획서를 확인하고 승인해주세요", "홍보물을 만들어줍니다")
    steps = "".join(f"<li><span>{i:02d}</span>{text}</li>" for i, text in enumerate(guide, 1))
    return (
        '<div class="fl-settings">'
        '<h2>설정</h2>'
        '<section class="fl-settings-card" aria-label="AI 설정 상태">'
        '<div class="fl-settings-label">AI 설정'
        f'<span class="fl-settings-state{"" if has_llm else " off"}">{state}</span></div>'
        f'<h3>{title}</h3><p>{description}</p></section>'
        '<section class="fl-settings-guide" aria-label="이용 순서">'
        f'<h3>이렇게 사용해주세요</h3><ol>{steps}</ol></section>'
        '<p class="fl-settings-foot">전국 축제에서 아이디어를 찾고,<br>'
        '제주 데이터로 우리 동네에 맞게 다듬어요.</p></div>'
    )


def head_html(step: int, title: str | None = None, desc: str | None = None) -> str:
    """단계 0n / 05 — 단계 이름 + 큰 제목 + 설명."""
    default_title, default_desc = STEP_TITLES[step]
    name = screen.STEPS[step - 1]
    return (
        f'<div class="fl-head"><div class="fl-eyebrow">단계 {step:02d} / {len(screen.STEPS):02d}'
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
    label = "데이터" if kind == "사실" else kind
    return f'<span class="fl-tag {EVIDENCE_TONE[kind]}">{escape(label)}</span>'


def check_head_html(label: str, status: str, synthetic: bool) -> str:
    extra = " " + tag_html("가상 데이터") if synthetic else ""
    return (
        f'<div class="fl-check-head"><span class="fl-check-title">{check_icon_html(label)}'
        f'<b>{escape(label)}</b></span>'
        f"<span>{badge_html(status)}{extra}</span></div>"
    )


def check_icon_html(label: str) -> str:
    names = {"시기": "timing", "장소": "venue", "대상": "target", "위험": "risk",
             "규모": "budget", "주의할 점": "warning", "SNS 글": "sns", "안내": "sparkle"}
    path = Path(__file__).resolve().parents[1] / "assets" / "icons" / f"{names[label]}.svg"
    uri = "data:image/svg+xml;base64," + b64encode(path.read_bytes()).decode("ascii")
    return f'<span class="fl-check-icon"><img src="{uri}" alt=""></span>'


def check_metric_html(summary: dict) -> str:
    synthetic = tag_html("가상 데이터") if summary["synthetic"] else ""
    return (
        '<div class="fl-check-metric">'
        f'<strong>{escape(summary["value"])}</strong><div>{synthetic}'
        f'<span>{escape(summary["label"])}</span></div></div>'
    )


def check_warning_html(warning: str) -> str:
    return (
        '<div class="fl-check-warning"><div class="fl-check-warning-title">'
        f'{check_icon_html("주의할 점")}주의할 점</div><p>{escape(warning)}</p></div>'
    )


# ---------- 05 홍보물 ----------


def sns_head_html(length: int | None) -> str:
    count = f'<span class="fl-count">{length}자</span>' if length is not None else ""
    return (
        f'<div class="fl-card-head"><span class="fl-check-title">{check_icon_html("SNS 글")}'
        f"<b>SNS 글</b></span>{count}</div>"
    )


def sns_body_html(text: str) -> str:
    return f'<div class="fl-sns-body">{escape(text)}</div>'


def copy_button_html(text: str) -> str:
    """'문구 복사' 버튼. components.html(iframe) 안에서 클립보드에 복사한다."""
    import json

    return f"""
<style>
  body {{ margin: 0; font-family: {_FONT}; }}
  button {{ background: #121212; color: #fff; border: none; border-radius: 8px;
    padding: 0 20px; height: 40px; font: inherit; font-size: 11.7px; cursor: pointer; }}
  button:hover {{ background: #333; }}
</style>
<button id="copy" type="button">문구 복사</button>
<script>
const text = {json.dumps(text)};
const btn = document.getElementById("copy");
btn.addEventListener("click", async () => {{
  try {{ await navigator.clipboard.writeText(text); }}
  catch (e) {{
    const t = document.createElement("textarea");
    t.value = text; document.body.appendChild(t); t.select();
    document.execCommand("copy"); t.remove();
  }}
  btn.textContent = "복사했어요";
  setTimeout(() => (btn.textContent = "문구 복사"), 1500);
}});
</script>
"""


def promo_checks_html(checks) -> str:
    rows = "".join(
        f'<li>{"✅" if c.ok else "⚠️"} <span>{escape(c.item)}: {escape(c.detail)}</span></li>'
        for c in checks
    )
    return (
        '<div class="fl-card-head"><b>정보 일치 검사</b>'
        '<small>기획서와 같은지 · 포스터와 SNS 글 각각</small></div>'
        f'<ul class="fl-promo-checks">{rows}</ul>'
        '<p class="fl-promo-note">다른 곳이 있으면 ⚠️로 표시해요. '
        "기획서에서 미확인인 날짜·장소는 두 곳 모두 ‘추후 공지’로 써요.</p>"
    )


def promo_files_html(has_sns: bool) -> str:
    files = ["poster.png", *(["sns.txt"] if has_sns else []), "plan.md (ZIP만)"]
    return (
        '<div class="fl-promo-files"><small>저장되는 파일</small>'
        + "".join(f"<span>{escape(f)}</span>" for f in files)
        + "</div>"
    )


def promo_info_html() -> str:
    return (
        f'<div class="fl-promo-info">{check_icon_html("안내")}<span>'
        "저장 위치는 outputs/ 폴더예요. 포스터와 SNS 문구는 같은 기획서 버전으로 묶어 저장해요. "
        "에이전트는 SNS 게시, 메일 전송, 광고 등록을 하지 않아요.</span></div>"
    )


def round_row_html(row: dict, last: bool) -> str:
    """타임라인 회차 줄: 점 + "처음 확인" + 항목별 배지. 마지막(지금 결과)은 주황 점."""
    items = "".join(
        f'<span class="fl-round-item">{escape(label)} {badge_html(status)}</span>'
        for label, status in row["items"]
    )
    now = '<span class="fl-round-now">지금 결과</span>' if last else ""
    return (
        f'<div class="fl-round{" last" if last else ""}"><span class="fl-round-dot"></span>'
        f'<b>{escape(row["label"])}</b>{now}<div class="fl-round-items">{items}</div></div>'
    )


def check_selection_html(card) -> str:
    """03 상단: 고른 아이디어 카드 (형식 × 재료, 제목, 한 줄 컨셉)."""
    return (
        '<section class="fl-check-selection" aria-label="고른 아이디어">'
        '<div class="fl-check-selection-label">고른 아이디어</div>'
        f'<div class="fl-check-selection-body"><h2>{escape(card.title)}</h2>'
        f'{format_html(f"{card.format} × {card.material}")}</div>'
        f'<p>{escape(card.concept)}</p></section>'
    )


def plan_strip_html(name: str, card, ready: bool) -> str:
    """추천안·고친 안의 조건(개최 월·장소·규모)과 진행 가능 여부."""
    venue = ", ".join(v.name for v in card.venue) or screen.NO_VENUE
    scale = screen.SCALE_LABELS.get(card.budget.scale, card.budget.scale)
    cells = (
        ("개최 월", screen.months_text(card.timing.recommended_months)),
        ("장소", venue),
        ("규모", scale),
    )
    state = (
        '<span class="fl-badge pass">진행 가능</span>' if ready
        else '<span class="fl-badge fail">진행 불가</span>'
    )
    return (
        f'<div class="fl-plan-strip" aria-label="{escape(name)} 조건">'
        f'<div class="fl-plan-strip-name"><small>{escape(name)}</small>{state}</div>'
        + "".join(
            f'<div class="fl-plan-strip-cell"><small>{label}</small><b>{escape(value)}</b></div>'
            for label, value in cells
        )
        + "</div>"
    )


def section_html(label: str) -> str:
    return f'<div class="fl-section">{escape(label)}</div>'


def format_html(text: str) -> str:
    return f'<span class="fl-format">{escape(text)}</span>'


# 축제 형식(FestivalFormat) → Figma 99 컴포넌트 「Pixel Glyph」 아이콘 (assets/icons/formats/)
FORMAT_ICONS = {
    "시장·상권": "market",
    "푸드·디저트": "dessert",
    "정원·가드닝": "garden",
    "여름·물놀이": "water",
    "맥주·주류": "drinks",
    "도심·거리·골목": "street",
    "야간·빛·드론": "night",
    "영화·책·아트": "art",
}


def format_icon_html(festival_format: str) -> str:
    """축제 형식 아이콘. 대응하는 아이콘이 없으면 빈 문자열 (카드는 그대로 보인다)."""
    name = FORMAT_ICONS.get(festival_format)
    if name is None:
        return ""
    path = Path(__file__).resolve().parents[1] / "assets" / "icons" / "formats" / f"{name}.svg"
    uri = "data:image/svg+xml;base64," + b64encode(path.read_bytes()).decode("ascii")
    return f'<img class="fl-format-icon" src="{uri}" alt="" width="40" height="40">'


def idea_card_head_html(card) -> str:
    """02 아이디어 카드 윗줄: 왼쪽 '형식 × 재료' 칩, 오른쪽 형식 아이콘."""
    return (
        '<div class="fl-idea-card-head">'
        f'{format_html(f"{card.format} × {card.material}")}{format_icon_html(card.format)}</div>'
    )


HERO = (
    '<div class="fl-hero">'
    '<div class="side"><small>함께 기획하는</small><b>우리 동네</b></div>'
    '<div class="fl-orb"><div class="sq"></div><div class="hole"></div><div class="plus"></div>'
    '<span class="tag" style="left:-30px;top:-14px">#애월 감귤</span>'
    '<span class="tag" style="right:-50px;top:40px">#대정 방어</span>'
    '<span class="tag" style="right:-6px;bottom:-16px">#성산 유채</span></div>'
    '<div class="side right"><small>제주 축제 메이커</small><b>축제 만들기</b></div></div>'
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
