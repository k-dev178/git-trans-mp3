export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"

soundnote_require_python() {
  if [[ ! -x .venv/bin/python ]]; then
    print '맥설치.command를 먼저 실행해 주세요.'
    read -r '?Enter를 누르면 닫힙니다. '
    exit 1
  fi
}

soundnote_failure() {
  print '\n작업에 실패했습니다. 위의 오류 메시지를 확인해 주세요.'
  read -r '?Enter를 누르면 닫힙니다. '
  exit 1
}
