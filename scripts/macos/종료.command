#!/bin/zsh
set -eu
cd "$(dirname "$0")/../.."
source scripts/macos/common.zsh
soundnote_require_python
.venv/bin/python -m soundnote --stop
