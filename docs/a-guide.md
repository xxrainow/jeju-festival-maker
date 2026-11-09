# A 기능 사용 안내 (B용)

아이디어 카드 3장을 받아오고, 고른 아이디어를 검증·수정하는 방법이다. 함수는 `agent/`에 있다.

> 계약은 합의 전까지 `agent/draft_contracts.py`(v2 초안)를 쓴다. 모양은 `docs/contract-v2-proposal.md` 참고.
> `schemas/contracts.py`로 옮기면 import 경로만 바뀐다.

## 1. 아이디어 카드

```python
from agent.draft_contracts import UserRequest
from agent.proposals import propose_idea_cards

request = UserRequest(region="제주시 애월읍", purpose="지역 상권 활성화", interest="감귤",
                      budget_max_krw=10_000_000, season="겨울", target="가족")
proposal = propose_idea_cards(request, demo=True)   # LLM 연결 전에는 demo=True

for notice in proposal.notices:                     # 데모 안내, 데이터 대기 안내
    st.info(notice)

for card in proposal.ideas:                         # 정확히 3장, rank 순서
    st.subheader(card.title)
    st.write(card.concept)
    st.caption(f"{card.format} × {card.material}")
    ev = card.evidence
    st.write("요즘 뜨는 형식:", f"신설 {ev.trend.new_count}개, 리프트 {ev.trend.new_lift}", ev.trend.source)
    st.write("제주 같은 형식 축제:", f"{ev.jeju_gap.jeju_count}개", ev.jeju_gap.source)
    if ev.visitor_interest.status == "pending":
        st.write("관광객 관심: 데이터 대기")
    st.write(card.reference.type, [f.name for f in card.reference.designated_festivals])
    st.write("추천 시기:", card.timing.recommended_months)
    st.write("검증할 가설:", card.hypotheses)
```

- `rank`, `score`는 화면에 보여주지 않는다 (순서에만 쓴다)
- 숫자 칸에는 `source`가 있다. 숫자와 함께 출처를 보여준다
- `status`가 `"pending"`인 근거는 값 대신 "데이터 대기"로 표시한다
- `is_demo`가 `True`면 `notices`를 빼지 말고 보여준다
- `st.session_state`에는 `proposal.model_dump(mode="json")`로 저장하고 `IdeaProposal.model_validate(...)`로 읽는다

## 2. 검증·수정 (아이디어 선택 후)

```python
from agent.fake_checks import FAKE_TOOLS          # B의 실제 도구가 생기면 교체
from agent.verify import summarize, verify_idea

run = verify_idea(card, request, FAKE_TOOLS)
for r in run.rounds[-1].results:                   # 마지막 라운드의 확인 5개
    st.write(r.check, r.status, r.reason)          # pass ✅ / conditional ⚠️ / fail ❌ / pending 데이터 대기
for line in summarize(run):                        # 바뀐 점과 이유
    st.write(line)
if run.outcome == "ready_for_approval":
    st.button("이대로 진행")
else:
    st.warning("다른 아이디어를 골라보세요.")
```

- 확인 도구는 `(IdeaCard, UserRequest) -> CheckResult` 함수다. `verify_idea`에 이름별 dict로 넘긴다
- 연결하지 않은 도구는 `pending`으로 남고 실패로 세지 않는다
- `is_synthetic=True`인 결과(가짜 도구 포함)는 화면에 가짜 데이터임을 드러낸다

## 3. 오류

- `propose_idea_cards(..., demo=False)`에 LLM을 넘기지 않으면 `CardGenerationError`
- 축제 패널(`data/processed/festival_panel_2024_2026.parquet`)이 없어도 `CardGenerationError`. 만드는 방법은 메시지에 있다
- `CardGenerationError`의 메시지는 화면에 그대로 보여줘도 되는 문장이다
