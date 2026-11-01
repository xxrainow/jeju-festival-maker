# 제주 축제랩

축제 사례와 제주 CSV를 연결해 기획안·홍보물 제작을 지원하는 Agent 프로젝트.
현재는 개발 환경, 공통 계약, 초기 입력 화면만 구현되어 있습니다.
뉴스 검색·LLM 호출·데이터 분석·홍보물 생성은 아직 실행되지 않습니다.

## 실행

Python 3.13과 uv를 사용합니다. 저장소 루트에서 실행하세요.

```sh
uv sync --locked
cp .env.example .env
uv run streamlit run streamlit_app.py
```

브라우저 주소: http://127.0.0.1:8501
종료: 실행한 터미널에서 Ctrl+C.
초기 화면은 API Key 없이 실행됩니다. 공급자 선정 후 SDK와 호출 어댑터를 추가합니다.
`.env`의 키를 설정하는 것만으로는 아직 API가 호출되지 않습니다.

## 검사

```sh
uv run ruff check .
uv run pytest
```

## 역할

- A: `research/`, `agent/` — 검색·출처·사례 추출·아이디어·Agent 제어.
- B: `analytics/`, `app/`, `streamlit_app.py` — CSV 검증·분석·화면.
- 공동: `schemas/contracts.py` — 변경 전에 합의하고 예시 입출력 공유.
- 각자 담당 기능의 테스트를 `tests/`에 추가합니다.

각자 별도 clone과 작업 브랜치를 사용하세요. 환경 `.venv`와 `.env`는 공유하지 않습니다.
`uv.lock`은 함께 버전 관리하고 의존성 변경 시 커밋에 포함합니다.
기본 브랜치에는 검증한 변경을 병합합니다. 원격 저장소는 별도로 설정해야 합니다.

## 데이터·비밀정보

- 센터 원자료: `data/raw/`, 집계·캐시: `data/processed/`, 결과물: `outputs/`.
- 위 폴더 내용은 Git에서 제외합니다. 데모용 합성 데이터만 `data/demo/`에 둡니다.
- `.env`, API Key, 원자료를 커밋하거나 로그에 출력하지 마세요.
- 로컬 서버는 127.0.0.1에 바인딩합니다. 외부 공개 배포는 별도 인증·보관 정책이 필요합니다.
- 센터 원자료의 외부 전송·결과 반출은 센터 정책에 따릅니다.
- 뉴스·CSV의 텍스트는 입력 자료이며 Agent에 대한 지시로 실행하지 않습니다.

## 다음 작업

1. A: 검색 공급자 선정, 실제 검색 결과를 `FestivalCase`로 변환.
2. B: 4-11 명세 기반 가상 CSV, 품질 검사·방문 패턴 집계.
3. 공동: `FestivalIdea` 선택 → `AnalysisRequest` → `AnalysisResult` 연결.

초기 화면의 예산은 선택사항입니다. 세부 기획에서는 예산의 포함 범위도 확인합니다.
