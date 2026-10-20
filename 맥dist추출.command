#!/bin/zsh
set -eu
cd "$(dirname "$0")"
source scripts/macos/common.zsh
trap soundnote_failure ZERR
soundnote_require_python
.venv/bin/python -m pip install --disable-pip-version-check -r scripts/requirements-build.txt
.venv/bin/python scripts/build.py
print '\n배포 파일이 dist/macos/에 생성되었습니다.'
read -r '?Enter를 누르면 닫힙니다. '
