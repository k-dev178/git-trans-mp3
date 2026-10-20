# 배포 파일 만들기

설치를 마친 **해당 운영체제**에서 루트의 dist 추출 파일을 실행합니다.
PyInstaller는 Python·Qt·whisper.cpp·FFmpeg를 함께 담습니다. 모델과 개인 `data/`는
포함하지 않으며, 배포본 사용자는 Python이나 Homebrew를 설치할 필요가 없습니다.

| 빌드 환경 | 실행 파일 | 결과 |
| --- | --- | --- |
| macOS | `맥dist추출.command` | `dist/macos/Soundnote.app`, `Soundnote-macos-<아키텍처>.zip` |
| Windows x64 | `윈도우dist추출.bat` | `dist/windows/Soundnote/Soundnote.exe`, `Soundnote-windows-x64.zip` |

맥에서 윈도우 EXE를 만들거나 윈도우에서 맥 앱을 만들 수 없습니다.
맥 빌드는 현재 Python과 네이티브 도구의 아키텍처를 따릅니다. Apple Silicon과 Intel
배포본이 각각 필요하면 해당 아키텍처의 맥에서 각각 빌드하세요.
Windows는 현재 x64 CPU 빌드이며 CUDA를 필수로 요구하지 않습니다.

Windows 배포 시에는 `Soundnote/` **폴더 전체** 또는 ZIP을 전달하세요.
`Soundnote.exe`만 옮기면 실행되지 않습니다. 맥은 `.app` 또는 ZIP을 전달합니다.
맥 배포본은 로컬 빌드이며 Apple Developer 서명·공증·DMG 생성은 포함하지 않습니다.

수동 빌드와 입력 확인:

```sh
# macOS; Windows에서는 .venv\Scripts\python.exe 사용
.venv/bin/python -m pip install -r scripts/requirements-build.txt
.venv/bin/python scripts/build.py --plan
.venv/bin/python scripts/build.py
```

배포본 데이터는 맥 `~/Library/Application Support/Soundnote/`, 윈도우
`%LOCALAPPDATA%\Soundnote\`에 저장됩니다. 개발용 `data/`는 그대로 유지됩니다.
기존 소스의 기록을 그대로 사용하려면 `SOUNDNOTE_DATA_DIR` 환경변수 또는
`--data-dir`로 기존 `data/`의 절대 경로를 지정하세요. DB에는 음성 사본의 절대
경로가 저장되므로 폴더만 복사해 다른 위치나 운영체제로 옮기는 방식은 지원하지 않습니다.

빌드 후에는 다른 사용자 환경에서 앱 열기, 짧은 음성 전사, 자동 언어 감지,
TXT·SRT 저장, 창 재열기·완전 종료를 확인하세요. `--plan`과 자동 테스트만으로
실제 Windows 실행이나 독립 배포를 검증할 수는 없습니다.

의존 구성요소와 배포 관련 정보는 [THIRD_PARTY.md](THIRD_PARTY.md)를 참고하세요.
