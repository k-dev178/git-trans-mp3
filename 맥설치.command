#!/bin/zsh
set -eu
cd "$(dirname "$0")"
source scripts/macos/common.zsh
trap soundnote_failure ZERR

soundnote_python=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(not ((3,10) <= sys.version_info[:2] <= (3,13)))' 2>/dev/null; then
    soundnote_python="$candidate"
    break
  fi
done
if [[ -z "$soundnote_python" ]]; then
  print 'Python 3.10~3.13이 필요합니다. python.org에서 Python 3.13을 설치해 주세요.'
  soundnote_failure
fi
if [[ ! -x .venv/bin/python ]]; then
  "$soundnote_python" -m venv .venv
fi
.venv/bin/python -c 'import sys; sys.exit(not ((3,10) <= sys.version_info[:2] <= (3,13)))'
.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
if ! command -v whisper-cli >/dev/null 2>&1 || ! command -v ffmpeg >/dev/null 2>&1; then
  if ! command -v brew >/dev/null 2>&1; then
    print 'Homebrew가 필요합니다. https://brew.sh 에서 설치 후 다시 실행하세요.'
    soundnote_failure
  fi
  brew install whisper.cpp ffmpeg
fi
print '\n설치 완료! 맥실행.command를 더블클릭하세요. 모델은 처음 사용할 때 다운로드됩니다.'
read -r '?Enter를 누르면 닫힙니다. '
