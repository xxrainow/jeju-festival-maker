# 설치·실행 안내

macOS와 Windows 11에서 제주 축제랩을 설치하고 실행하는 방법입니다. 명령어는 그대로 복사해 붙여 넣으면 됩니다.

## 0. 준비물

| 항목 | 내용 |
|---|---|
| 컴퓨터 | 센터 PC 최소 사양(Intel Core i7-8700, RAM 32GB)에서 돌아갑니다. **GPU는 쓰지 않습니다** (아래 설명) |
| 인터넷 | **설치할 때 필요**합니다. 실행 중에는 AI 기능(한 문장 정리, 아이디어 카드, 기획서, SNS 글, 포스터 그림)에만 필요합니다 |
| 프로그램 폴더 | 제출 ZIP을 푼 폴더 또는 Git 저장소 (`jeju-festival-maker`) |
| Gemini API 키 | AI 기능을 쓸 때 필요합니다 (3절). 키가 없어도 화면은 열리고 예시 카드로 흐름을 볼 수 있습니다 |

### GPU가 필요 없는 이유

- AI 문장 생성은 Google Gemini(외부 서비스)가 하고, 이 PC는 결과만 받습니다. 큰 AI 모델을 PC에서 돌리지 않습니다.
- 데이터 확인·집계·계산은 모두 CPU로 합니다. 확인 도구 5개는 한 번에 보통 1~10초 걸립니다.
- 센터 PC의 GTX 1060은 쓰지 않아도 됩니다.

## 1. 설치

`uv`는 파이썬과 필요한 패키지를 한 번에 설치해 주는 도구입니다. 파이썬을 따로 설치하지 않아도 됩니다. `uv`가 이 프로그램에 맞는 Python 3.13을 내려받습니다.

### macOS

1. **터미널**을 엽니다 (Spotlight에서 "터미널" 검색).
2. uv를 설치합니다.

   ```sh
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. 터미널을 닫았다가 다시 엽니다. `uv --version`을 입력해 버전이 나오면 설치된 것입니다.
4. 프로그램 폴더로 이동합니다 (폴더 위치에 맞게 바꾸세요).

   ```sh
   cd ~/Desktop/jeju-festival-maker
   ```

5. 패키지를 설치합니다. 처음 한 번만 하면 되고, 몇 분 걸릴 수 있습니다.

   ```sh
   uv sync --locked
   ```

6. 설정 파일을 만듭니다.

   ```sh
   cp .env.example .env
   ```

### Windows 11

1. 시작 메뉴에서 **PowerShell**을 엽니다.
2. uv를 설치합니다.

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

3. PowerShell을 닫았다가 다시 엽니다. `uv --version`을 입력해 버전이 나오면 설치된 것입니다.
4. 프로그램 폴더로 이동합니다 (폴더 위치에 맞게 바꾸세요).

   ```powershell
   cd $HOME\Desktop\jeju-festival-maker
   ```

5. 패키지를 설치합니다.

   ```powershell
   uv sync --locked
   ```

6. 설정 파일을 만듭니다.

   ```powershell
   copy .env.example .env
   ```

- `uv sync --locked`는 `uv.lock`에 적힌 버전 그대로 설치합니다. 개발할 때와 같은 환경이 됩니다.
- 설치는 프로그램 폴더 안 `.venv` 폴더에만 됩니다. 컴퓨터의 다른 프로그램에는 영향이 없습니다.

## 2. .env 설정

`.env`는 키와 설정을 적는 파일입니다. 메모장(Windows)이나 텍스트 편집기(macOS)로 엽니다.

- 파일 이름이 점(.)으로 시작해 폴더에서 안 보일 수 있습니다.
  - macOS Finder: `Cmd + Shift + .`
  - Windows 탐색기: 보기 → 표시 → 숨긴 항목
- 저장은 **UTF-8**로 하세요 (Windows 11 메모장은 기본이 UTF-8).

```
LLM_PROVIDER=gemini
LLM_MODEL=
LLM_API_KEY=여기에-발급받은-키
IMAGE_MODEL=

JEJU_HUB_KEY=

MAX_AGENT_STEPS=6
REQUEST_TIMEOUT_SECONDS=30
```

| 항목 | 필수 | 설명 |
|---|---|---|
| `LLM_PROVIDER` | AI를 쓸 때 | `gemini`로 둡니다. 다른 값이거나 비어 있으면 AI 기능이 꺼집니다 |
| `LLM_MODEL` | 아니요 | 문장을 쓰는 Gemini 모델 이름. **비워 두면 `gemini-3.5-flash-lite`**. 포스터 글자 검사에도 같은 모델을 씁니다 |
| `LLM_API_KEY` | AI를 쓸 때 | Google AI Studio에서 받은 키 (3절). 화면·로그에는 표시하지 않습니다 |
| `IMAGE_MODEL` | 아니요 | 포스터 그림 모델. **비워 두면 `gemini-3.1-flash-lite-image`**. 키는 `LLM_API_KEY`를 같이 씁니다. 결제 설정한 키만 쓸 수 있습니다 |
| `JEJU_HUB_KEY` | 아니요 | 제주데이터허브 API 키. 개발자가 원자료를 다시 받을 때만 씁니다 (`analytics/fetch_jeju_hub.py`). 일반 사용에는 필요 없습니다 |
| `MAX_AGENT_STEPS` | 아니요 | 예약 값입니다. 지금 버전에서는 쓰지 않습니다 (고치고 다시 확인하는 횟수는 코드에서 최대 3번) |
| `REQUEST_TIMEOUT_SECONDS` | 아니요 | AI 응답을 기다리는 최대 시간(초). 기본 30. 1~120 |

**키 관리**
- **GitHub(Git 저장소)에는 어떤 키도 절대 올리지 않습니다.** `.env`는 Git에서 빠져 있습니다.
- **개인 키**: 개발자가 쓰던 개인 키가 든 `.env`는 제출 ZIP에 넣지 않습니다.
- **평가용 키**: 공모전 규칙에 따라 평가용 키만 제출 ZIP의 `.env`에 넣습니다.
  - 평가용 키는 Google Cloud에서 사용 한도를 걸어 둔 별도 키입니다.
  - 평가가 끝나면 폐기합니다.
  - 평가하는 분은 ZIP을 풀고 바로 실행하면 됩니다. 2절의 `.env` 만들기는 건너뛰세요.
- 키를 다른 사람에게 메일·메신저로 보내지 마세요.

## 3. Gemini API 키 받기 (Google AI Studio)

1. https://aistudio.google.com 에 Google 계정으로 로그인합니다.
2. 왼쪽 메뉴의 **Get API key**(API 키 받기)를 누릅니다.
3. **Create API key**(API 키 만들기)를 누르고 프로젝트를 고릅니다. 없으면 새로 만듭니다.
4. 만들어진 키를 복사해 `.env`의 `LLM_API_KEY=` 뒤에 붙여 넣고 저장합니다. 앞뒤에 빈칸이나 따옴표를 넣지 마세요.
5. 프로그램을 다시 실행하면 설정 패널에 "AI 설정 · 사용 가능"이 나옵니다.

### 비용과 무료 사용량

| 기능 | 모델 | 무료 키로 | 한 번 쓸 때 AI 호출 수 |
|---|---|---|---|
| 한 문장 정리 | `LLM_MODEL` | 됩니다 | 1~2번 |
| 아이디어 카드 | `LLM_MODEL` | 됩니다 | 1~2번 (다시 받기마다 1~2번 더) |
| 기획서 | `LLM_MODEL` | 됩니다 | 1~2번 |
| SNS 글 | `LLM_MODEL` | 됩니다 | 1~3번 |
| 포스터 그림 | `IMAGE_MODEL` | **안 됩니다.** 결제 설정한 키만 | 그림 1~4장 + 글자 읽기 1~3번 |

- 실제 시험(2026-11-17~18)에서 조건 입력부터 홍보물까지 한 번 끝까지 하는 데 텍스트 AI 호출이 **4~10번** 들었습니다(포스터 그림 제외).
- 무료 사용량과 요금은 Google 정책에 따라 바뀝니다. 최신 내용은 AI Studio의 요금 안내에서 확인하세요.
- 무료 사용량을 넘으면 "오늘 AI 사용 한도를 넘었어요. 잠시 뒤 다시 해보세요."가 나옵니다 ([troubleshooting.md](troubleshooting.md)).
- **포스터 그림을 쓰려면** Google Cloud 프로젝트에 결제 계정을 연결한 키가 필요합니다.
  - 무료 키여도 포스터는 기본 포스터(단색 바탕 + 글자)로 만들어집니다.
  - 화면에 그림 설명이 나오니, 복사해서 AI Studio에서 직접 그림을 만들 수 있습니다.

## 4. 실행

프로그램 폴더에서 다음을 입력합니다 (macOS·Windows 같음).

```sh
uv run streamlit run streamlit_app.py
```

- 터미널에 `URL: http://127.0.0.1:8501`이 나오면 준비된 것입니다.
- **브라우저는 자동으로 열리지 않습니다.** 브라우저(Chrome, Edge 등)를 열고 주소창에 **http://localhost:8501** 을 직접 입력하세요. 안 열리면 **http://127.0.0.1:8501** 을 입력하세요.
- 첫 실행 때 이메일을 묻는 영어 질문은 나오지 않습니다 (`.streamlit/config.toml`의 `headless = true`).
- 이 주소는 **이 컴퓨터에서만** 열립니다. 다른 컴퓨터에서는 접속할 수 없습니다.
- 사용법은 [manual.md](manual.md)를 보세요.

## 5. 종료

1. 브라우저 탭을 닫습니다.
2. 실행한 터미널(PowerShell)에서 **Ctrl + C**를 누릅니다. 명령 입력 줄이 다시 나오면 꺼진 것입니다.

만든 기획서와 포스터는 꺼도 남습니다.
- 기획서: `outputs/plans/`
- 포스터: `outputs/promo/`

## 6. 설치가 잘 됐는지 확인 (선택)

```sh
uv run pytest
```

마지막 줄에 `444 passed`처럼 `passed`만 나오면 정상입니다. 인터넷과 AI 키 없이 돌아갑니다.

## 7. 의존성 목록

`pyproject.toml` 기준입니다. 괄호 안은 `uv.lock`에 고정된 실제 설치 버전입니다.

| 패키지 | 버전 범위 (설치 버전) | 용도 |
|---|---|---|
| streamlit | ≥1.40, <2 (1.66.1) | 화면 (웹 브라우저로 보는 앱) |
| pandas | ≥2.2, <3 (2.3.3) | 표 데이터 읽기·집계 |
| duckdb | ≥1.1, <2 (1.5.6) | 큰 CSV(버스 이용 596MB 등)를 빠르게 읽고 집계 (원자료로 가공본을 다시 만들 때) |
| pydantic | ≥2.10, <3 (2.14.2) | 단계 사이 데이터 형식(조건, 카드, 확인 결과, 기획서) 검사 |
| pydantic-settings | ≥2.6, <3 (2.16.2) | `.env` 설정 읽기 |
| httpx | ≥0.27, <1 (0.28.1) | Gemini API, 제주데이터허브 API 호출 |
| pillow | ≥11, <14 (13.0.0) | 포스터 그림 만들기·한글 글자 얹기 |
| shapely | ≥2.2.0 (2.2.0) | 행정동 경계 안에 장소 좌표가 들어가는지 판정 |
| plotly | ≥5.24, <7 (6.9.0) | 시간대별 방문 패턴 그래프 (분석용) |
| openpyxl | ≥3.1.5 (3.1.5) | 문체부 지역축제 엑셀(.xlsx) 읽기 |
| xlrd | ≥2.0.2 (2.0.2) | 전국문화축제표준데이터 엑셀(.xls) 읽기 |
| python-docx | ≥1.2, <2 (1.2.0) | 기획서 Word(.docx) 내려받기 |
| python-hwpx | ≥2, <7 (6.12.0) | 기획서 한글(.hwpx) 내려받기 |
| markdown-it-py | ≥3, <5 (4.3.0) | 기획서 문서 화면·수정한 Markdown 읽기 |
| pytest (개발용) | ≥8, <10 (9.2.0) | 자동 테스트 |
| ruff (개발용) | ≥0.9, <1 (0.17.3) | 코드 검사 |

- 파이썬 버전: 3.13 (`.python-version`). `pyproject.toml`은 3.11~3.13을 허용합니다.
- 포스터 한글 글꼴은 저장소에 포함된 Noto Sans KR Bold(`assets/fonts/`, SIL Open Font License 1.1)를 씁니다. 따로 설치할 필요가 없습니다.
- 원자료로 가공본을 다시 만들 때만 `python-calamine`을 임시로 씁니다 (`uv run --with python-calamine …`). 일반 실행에는 필요 없습니다.
