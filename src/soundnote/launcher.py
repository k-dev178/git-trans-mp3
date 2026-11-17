"""Start, reopen, or stop Soundnote without relying on platform PID signals."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from .instance import InstanceLock
from .paths import FROZEN, ROOT, data_directory


def data_locked(directory=None):
    with InstanceLock(directory or data_directory()) as lock:
        return not lock.acquire()


def running_desktop(directory=None):
    directory = directory or data_directory()
    try:
        info = json.loads((directory / "desktop-runtime.json").read_text(encoding="utf-8"))
        if info.get("app") == "soundnote-desktop" and info.get("workspace") == str(ROOT) and data_locked(directory):
            return info
    except (OSError, ValueError):
        pass
    return None


def main():
    parser = argparse.ArgumentParser(description="소리노트 GUI 실행 및 종료")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--foreground", action="store_true")
    parser.add_argument("--data-dir", type=Path, default=data_directory())
    args = parser.parse_args()
    directory = args.data_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    existing = running_desktop(directory)
    if args.stop:
        if existing:
            (directory / "stop-app").write_text(str(os.getpid()))
            print("소리노트를 종료합니다. 중단된 작업은 다음 실행 시 다시 시작됩니다.")
        else:
            print("실행 중인 소리노트 GUI가 없습니다.")
        return
    if existing:
        (directory / "show-window").write_text(str(time.time_ns()))
        return
    if data_locked(directory):
        sys.exit("다른 프로그램이 저장 폴더를 사용하고 있습니다. 기존 앱을 종료한 뒤 다시 열어 주세요.")
    if args.foreground or FROZEN:
        from .desktop import main as desktop_main
        sys.argv = [sys.argv[0], "--data-dir", str(directory)]
        desktop_main()
        return
    from .qt_bootstrap import ensure_qt
    if not ensure_qt():
        sys.exit("GUI 라이브러리가 필요합니다. README.md의 설치 명령을 실행하세요.")
    with (directory / "launcher.log").open("ab") as output:
        subprocess.Popen([sys.executable, "-m", "soundnote", "--foreground", "--data-dir", str(directory)],
                         cwd=ROOT, stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                         **({"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
                            if os.name == "nt" else {"start_new_session": True}))
    print("소리노트 GUI를 실행합니다. 완전 종료는 앱 메뉴를 사용하세요.")
