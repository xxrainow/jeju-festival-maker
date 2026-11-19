# 팀 작업 노트 (내부용)

README에서 옮긴 팀 내부 내용입니다. 제출 PDF(`scripts/make_pdfs.sh`)에는 들어가지 않습니다.
README는 심사위원이 읽는 제출 문서(01_README.pdf)라서 진행 상황·역할·남은 작업은 여기에 둡니다.

설계 상세는 설계 기획서(https://claude.ai/artifact/2TVHkNn8cKuxnahSgmaUvW)를 따릅니다.

## 지금 상태 (11/20)

| 기능 | 상태 |
|---|---|
| 한 문장 → 조건 칸 | 완료 (Gemini). AI 설정이 없으면 칸에 직접 입력 |
| 아이디어 카드 3장 | 완료 (Gemini). 카드가 규칙 검사에 걸리면 "다시 받기". 키 없음·한도 초과·연결 오류 때만 예시 카드(애월 감귤) |
| 시연 옵션 | 완료. 켜면 애월·겨울·감귤·가족·1,000만 원 조건을 채우고 AI 없이 예시 카드 |
| 확인 도구 5개 | 완료. 공개 데이터 가공본(실데이터)으로 계산. 4-11 유동인구, 3-04 시간대 버스, 3-07·3-08·3-10 교통은 명세서 구조의 가상 데이터라 화면에 "가상 데이터"로 표시 |
| 고치고 다시 확인 | 완료. 에이전트가 최대 3번 고치고, 사용자가 개최 월·장소·규모를 직접 바꿔 다시 확인할 수 있음. 고칠 제안이 없는 실패(예: 대상)가 섞여 있어도 제안이 있는 실패는 먼저 고침 |
| 기획서 생성·최종 승인 | 완료. 17개 항목, `outputs/plans/`에 저장. 실패하면 "다시 만들기" |
| 홍보물 | 완료. 포스터(1200×1600)·SNS 글·정보 일치 검사. **포스터 그림은 결제 설정한 Gemini 키가 필요**하고, 없으면 기본 포스터와 복사용 그림 설명을 보여줌 |
| 제출 문서 | 완료. `docs/submission/` (위 표) |
| 테스트 | `uv run pytest` 510개 통과 (11/20) |

## 폴더별 담당

| 경로 | 담당 | 내용 |
|---|---|---|
| `research/` | A | 문체부 축제 패널·형식 트렌드(`trends.py`), 지정 축제 연결(`designation.py`), 제주 재료 사전(`materials.py`) |
| `agent/` | A | 조건 추출(`request_parser.py`), 후보 점수(`idea_gen.py`), 카드 생성(`idea_cards.py`, `proposals.py`), 확인·수정 루프(`verify.py`), 기획안(`plan.py`), Gemini 호출(`gemini.py`), v2 계약 초안(`draft_contracts.py`) |
| `analytics/` | B | CSV 검증, 집계, 확인 도구 5개(`check_*.py`, `real_checks.py`), 후보지 비교, 예산 벤치마크, 날씨 |
| `app/`, `streamlit_app.py` | B | 설정, 화면 |
| `schemas/contracts.py` | 공동 | 공통 계약 |
| `tests/` | 각자 | 담당 기능 테스트 |
| `docs/` | 각자 | `a-guide.md`(A 기능 쓰는 법), `b-guide.md`(B 기능 쓰는 법), `contract-v2-proposal.md`, `data-check.md`(데이터 점검) |

## 역할

- A: `research/`, `agent/` — 트렌드·지정 축제, 아이디어 카드, 확인·수정 루프, 기획안, Agent 제어.
- B: `analytics/`, `app/`, `streamlit_app.py` — CSV 검증·분석, 확인 도구, 화면, 홍보물.
- 공동: `schemas/contracts.py` — 변경 전에 합의하고 예시 입출력 공유.
- 각자 담당 기능의 테스트를 `tests/`에 추가합니다.

각자 별도 clone과 작업 브랜치를 사용하세요. 환경 `.venv`와 `.env`는 공유하지 않습니다.
`uv.lock`은 함께 버전 관리하고 의존성 변경 시 커밋에 포함합니다.
main에 직접 push하지 않고 작업 브랜치 → main PR로 합칩니다.

## 원본이 바뀌었거나 키워드 표를 고쳤을 때 (원본을 가진 사람만)

1. 원본을 둡니다 (Git 제외)
   - 문체부 엑셀: `data/raw/mcst/mcst_2024.xlsx`, `mcst_2025.xlsx`, `mcst_2026.xlsx`
   - 와이파이 CSV 2개, 전국문화축제표준데이터: `data/raw/`
2. 다시 만들고 가공본도 갱신한 뒤, `research/reference/`의 바뀐 파일을 커밋합니다

```sh
uv run --with python-calamine python -m research.trends --publish
```

```sh
uv run python -m research.materials --publish
```

엑셀 읽기용 `python-calamine`은 가공본을 다시 만들 때만 필요해서 의존성에 넣지 않고 `--with`로 임시 설치합니다.

공개 데이터 전체를 원본부터 다시 만드는 순서는 `docs/submission/data-spec.md` 3-4절에 있습니다.

## 남은 작업 (11/20 기준)

1. 제출 준비
   - 사용자 매뉴얼의 [캡처] 13곳 채우기
   - 새 PC에서 설치·실행 확인, 제출 ZIP 구성 (`data/raw/`·`outputs/`·개인 키 제외, 평가용 키만 `.env`에 포함. GitHub에는 키를 올리지 않음)
   - `.env.example`의 `MAX_AGENT_STEPS`는 지금 코드에서 쓰지 않음 (수정 횟수는 `agent/verify.py`의 `MAX_FIXES = 3`). 지우거나 설명 달기
2. 데이터
   - 4-11 유동인구 실데이터가 오면 `data/raw/`에 넣어 가상 데이터와 교체하고 KPI 기준값 채우기
   - 1년치가 쌓이면 외지인 지수를 4-11로 다시 만들기
   - 제주 재료 사전에 없는 소재(고등어, 당근, 녹차, 보리 등) 추가 검토
   - 각 데이터의 이용허락 유형(공공누리 등)을 포털에서 확인해 `docs/submission/data-spec.md`에 넣기
3. A·B: v2 계약(`agent/draft_contracts.py`)을 `schemas/contracts.py`로 옮기기
