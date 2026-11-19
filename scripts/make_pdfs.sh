#!/usr/bin/env bash
# 제출 문서(md) → PDF 5개 (submission_pdf/). md 원본은 바꾸지 않는다.
# 실행 (프로그램 폴더 어디서나): bash scripts/make_pdfs.sh
#
# 필요한 것
# - uv (앱 설치 때 이미 있음). md → HTML은 앱 의존성인 markdown-it-py로 한다
# - Node.js와 Playwright(Chromium). 없으면 설치 방법을 안내하고 멈춘다
# - 본문 글꼴 Noto Sans KR Regular: 저장소에 넣지 않고, 없으면 공식 배포처(notofonts/noto-cjk, OFL)에서 받아 온다
#   (제목·굵은 글씨는 저장소의 assets/fonts/NotoSansKR-Bold.otf)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT="$ROOT/submission_pdf"
CACHE="$ROOT/.cache/submission_pdf"        # 글꼴·HTML·Playwright 설치 위치 (Git 제외)
NODE_DIR="$CACHE/node"
FONT="$CACHE/NotoSansKR-Regular.otf"
FONT_URL="https://github.com/notofonts/noto-cjk/raw/main/Sans/SubsetOTF/KR/NotoSansKR-Regular.otf"
PLAYWRIGHT_VERSION="1.49.1"
mkdir -p "$CACHE"

# 1) Node.js
if ! command -v node >/dev/null 2>&1; then
  echo "Node.js가 없어요. https://nodejs.org 에서 LTS 버전을 설치한 뒤 다시 실행해 주세요." >&2
  exit 1
fi

# 2) Playwright (이 폴더에 설치한 것 → 전역에 설치한 것 순서로 찾음)
export NODE_PATH="$NODE_DIR/node_modules${NODE_PATH:+:$NODE_PATH}"
if ! node -e "require.resolve('playwright')" >/dev/null 2>&1; then
  cat >&2 <<EOF
Playwright를 찾지 못했어요. 아래 두 줄을 실행해 설치한 뒤 다시 실행해 주세요 (Chromium 약 150MB를 받습니다).

  npm install --prefix "$NODE_DIR" playwright@$PLAYWRIGHT_VERSION
  npx --prefix "$NODE_DIR" playwright install chromium
EOF
  exit 1
fi

# 3) 본문 글꼴 (없으면 받아 옴)
if [ ! -s "$FONT" ]; then
  echo "본문 글꼴(Noto Sans KR Regular)을 받아 옵니다: $FONT_URL"
  if ! curl -fsSL -o "$FONT.part" "$FONT_URL"; then
    rm -f "$FONT.part"
    echo "글꼴을 받지 못했어요. 인터넷 연결을 확인하거나, 위 주소에서 받은 파일을 $FONT 에 두고 다시 실행해 주세요." >&2
    exit 1
  fi
  if [ "$(head -c 4 "$FONT.part")" != "OTTO" ]; then
    rm -f "$FONT.part"
    echo "받은 파일이 글꼴(OTF)이 아니에요. 잠시 뒤 다시 실행해 주세요." >&2
    exit 1
  fi
  mv "$FONT.part" "$FONT"
fi

# 4) md → HTML → PDF
uv run --quiet python scripts/pdf_build_html.py "$CACHE/html" "$FONT" > "$CACHE/jobs.json"
node scripts/pdf_render.js "$CACHE/jobs.json" "$OUT"
echo "완료: $OUT"
