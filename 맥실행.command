#!/bin/zsh
set -eu
cd "$(dirname "$0")"
source scripts/macos/common.zsh
trap soundnote_failure ZERR
soundnote_require_python
.venv/bin/python -m soundnote
