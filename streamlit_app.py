import streamlit as st

from app.settings import Settings
from schemas.contracts import UserRequest

st.set_page_config(page_title="제주 축제랩", page_icon="🍊", layout="wide")
settings = Settings()

st.title("🍊 제주 축제랩")
st.subheader("우리 지역에서 열어볼 만한 축제는?")
st.write("전국 축제 트렌드와 제주 데이터를 연결해 지역에 맞는 기획안을 준비합니다.")
st.info("개발 초기 화면입니다. 아이디어 제안·CSV 분석은 아직 연결되지 않았습니다.")

with st.form("initial_request"):
    region = st.text_input("희망 지역", placeholder="미정이면 비워두세요")
    purpose = st.selectbox(
        "축제 목적", ["지역 상권 활성화", "관광객 유치", "주민 참여", "아직 미정"]
    )
    interest = st.text_input("관심 소재 (선택)", placeholder="감귤, 음식, 문화, 자연 등")
    budget_known = st.checkbox("정해둔 예산 상한이 있어요")
    budget = st.number_input("예산 상한 (원)", min_value=1, value=10_000_000, step=100_000)
    st.caption("체크하지 않으면 예산은 미정으로 저장합니다. 초기에는 예산을 몰라도 됩니다.")
    submitted = st.form_submit_button("기획 조건 저장")

if submitted:
    request = UserRequest(
        region=region.strip() or None,
        purpose=purpose,
        interest=interest.strip() or None,
        budget_max_krw=budget if budget_known else None,
    )
    st.session_state["request"] = request.model_dump()
    st.success("기획 조건을 저장했습니다. 다음 개발 단계에서 사례 검색으로 연결합니다.")

if "request" in st.session_state:
    with st.expander("입력한 조건 확인", expanded=True):
        st.json(st.session_state["request"])

with st.sidebar:
    st.header("개발 상태")
    st.write("아이디어 카드: 연결 예정")
    st.write("제주 CSV 분석: 연결 예정")
    st.caption("API Key는 화면에 표시하지 않습니다.")
    st.write("LLM 키 설정:", "있음" if settings.llm_api_key.get_secret_value() else "없음")
