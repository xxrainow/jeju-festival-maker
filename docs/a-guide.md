# A 기능 사용 안내 (B용)

아이디어 카드 화면에서 축제 아이디어 3개를 받아오는 방법이다. 함수는 `agent/`에 있다.

> 이 안내는 jiwoo 브랜치의 계약 변경(`rationale`, `target_audience` 목록, `retrieved_at`)을 전제로 한다.
> 합의 전이므로 바뀌면 이 문서도 같이 고친다.

## 1. 흐름

```python
from agent.proposals import propose_ideas
from schemas.contracts import UserRequest

request = UserRequest(region="제주시 애월읍", purpose="지역 상권 활성화", interest="감귤")
proposal = propose_ideas(request, demo=True)   # 지금은 demo=True만 동작

for notice in proposal.notices:                # 데모 안내, 검토 전 안내
    st.info(notice)

for idea in proposal.ideas:                    # 정확히 3개
    st.subheader(idea.title)
    st.write(idea.summary)
    st.write("핵심 프로그램:", ", ".join(idea.programs))
    st.write("주 대상:", idea.target_audience[0])
    st.caption(idea.rationale)                 # 제주에 적용할 이유 (가설)
    for case in proposal.cases_for(idea):      # 이 아이디어가 인용한 사례
        st.caption(f"참고: [{case.title}]({case.source_url}) · 수집 {case.retrieved_at:%Y-%m-%d}")
```

`st.session_state`에 넣을 때는 `proposal.model_dump(mode="json")`로 저장하고
`IdeaProposal.model_validate(...)`로 다시 읽는다.

## 2. `IdeaProposal`

| 필드 | 내용 |
|---|---|
| `request` | 넘긴 `UserRequest` 그대로 |
| `ideas` | `FestivalIdea` 3개. `idea_id`는 `idea_001`~`idea_003`, `status`는 `"unreviewed"` |
| `cases` | 아이디어가 인용한 `FestivalCase`. 출처 링크·게시일·수집일 표시에 쓴다 |
| `is_demo` | `True`면 가상 자료. 화면에 데모임을 꼭 드러낸다 |
| `notices` | 화면에 그대로 보여줄 안내 문장 목록 |
| `cases_for(idea)` | 그 아이디어가 인용한 사례만 순서대로 |

## 3. 화면에서 지킬 것

- `is_demo`가 `True`면 `notices`를 빼지 말고 보여준다 (가상 자료 표시)
- 아이디어는 "데이터 검토 전" 상태다. 확정된 기획처럼 보이지 않게 한다
- `rationale`은 가설이다. "효과가 있다"처럼 단정하는 문구로 바꾸지 않는다
- 사례의 `evidence_status`가 `snippet_only`면 "요약만 확보"라고 함께 표시하면 좋다
- `target_audience`는 1~3개이고 첫 항목이 주 대상이다

## 4. 오류

- `propose_ideas(..., demo=False)`는 아직 연결 전이라 `IdeaGenerationError`를 던진다
- `IdeaGenerationError`의 메시지는 화면에 그대로 보여줘도 되는 문장이다

## 5. 앞으로 바뀌는 것

- `demo=False`에 실제 사례 검색(Tavily)과 AI 생성(Gemini 예정)이 붙는다. 호출 방법과 `IdeaProposal` 모양은 그대로 둔다
- 아이디어를 고른 뒤 `AnalysisRequest`를 만드는 함수를 추가할 예정이다 (지역은 B 데이터의 행정동명 기준)
