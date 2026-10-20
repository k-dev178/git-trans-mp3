# 소리노트

음성 파일을 텍스트로 전사하는 **데스크톱 GUI 프로그램**입니다. Qt 화면과 C++ whisper.cpp 엔진을 사용합니다. macOS와 Windows x64용 설치·실행·배포 스크립트를 제공합니다. Windows 실기기 검증은 별도로 필요합니다.

## 실행

| 운영체제 | 처음 설치 | 실행 | 배포 파일 생성 |
| --- | --- | --- | --- |
| macOS | `맥설치.command` | `맥실행.command` | `맥dist추출.command` |
| Windows x64 | `윈도우설치.bat` | `윈도우실행.bat` | `윈도우dist추출.bat` |

1. Python 3.10~3.13과 인터넷 연결이 필요합니다. 맥은 [Homebrew](https://brew.sh), 윈도우는 **64비트 Python**을 준비하세요. 윈도우 Python 설치 시 Python Launcher도 설치하세요.
2. 운영체제에 맞는 **설치** 파일을 실행한 뒤 **실행** 파일을 더블클릭합니다. 설치 파일은 GUI(PySide6), whisper.cpp, FFmpeg를 준비합니다. Windows 네이티브 도구는 프로젝트의 `tools/native/`에 저장되며 PATH에 설치된 도구도 사용할 수 있습니다.
3. 첫 화면에는 전사 리스트와 **+** 버튼만 표시됩니다. **+**를 누르면 파일 드롭 영역만 표시됩니다. **Esc**로 목록에 돌아갈 수 있습니다.
4. MP3·M4A 등 파일을 끌어다 놓거나 파일 선택 창에서 고릅니다. 유효한 파일을 고르면 모델·언어·세부 설정과 **확인 · 전사 시작** 버튼이 나타납니다.
5. 모델과 언어를 고르고 확인을 누르면 백그라운드 전사가 시작됩니다. **홈으로 돌아가기**를 누르면 목록에서 회전 로딩 표시와 진행률을 확인할 수 있습니다.
6. 완료된 기록을 클릭하면 전사 내용을 확인하고 복사하거나 TXT·SRT로 저장할 수 있습니다. 실패한 작업은 같은 화면에서 다시 시작할 수 있습니다.

독립 배포본은 맥에서 `dist/macos/Soundnote.app`, 윈도우에서 `dist/windows/Soundnote/Soundnote.exe`로 생성됩니다. 빌드는 **해당 운영체제에서** 실행해야 합니다. 폴더 전체 또는 ZIP을 배포하세요. 자세한 내용은 [배포 안내](docs/build.md)를 참고하세요.

## 폴더 구성

```text
src/soundnote/     GUI, 테마, 저장소, whisper.cpp 연동 코드
scripts/          설치·패키징 도구와 운영체제별 보조 스크립트
assets/           앱 아이콘
tests/            자동 테스트
docs/             배포 안내, 화면 예시, 기존 참고 파일
data/             기존 녹음 사본·전사 기록·모델 (개발 실행)
tools/native/     Windows용 whisper.cpp·FFmpeg (설치 시 생성)
build/, dist/     빌드 중간 파일, 배포 결과 (빌드 시 생성)
```

예전 소스 실행용 `.app`은 `scripts/macos/소리노트.app`에 보관했습니다. 루트의 `맥실행.command`를 사용하면 됩니다.

## 백그라운드 동작

- 앱 창의 닫기 버튼을 누르면 창이 숨겨지고 전사는 계속됩니다.
- 맥 메뉴 막대 또는 윈도우 알림 영역의 소리노트 아이콘에서 **전사 목록 열기**, **새 전사**, **소리노트 종료**를 선택할 수 있습니다.
- 앱을 다시 더블클릭하면 실행 중인 앱 창을 다시 엽니다. Dock에서 앱을 활성화해도 숨겨진 창이 다시 열립니다.
- 완전히 종료하려면 앱 메뉴의 **소리노트 종료**를 사용합니다. 맥은 Cmd+Q 또는 `scripts/macos/종료.command`도 사용할 수 있습니다.
- 컴퓨터가 잠자기 상태이면 처리도 멈춥니다. 종료로 중단된 전사는 다음 실행 시 원본 음성부터 다시 처리됩니다.

## 화면 모드

앱 메뉴의 **설정…** 또는 **⌘,**를 누르면 설정창이 열립니다. 메뉴 막대의 소리노트 아이콘에서도 설정을 열 수 있습니다.

- **시스템 설정 따르기 (기본값)**: 운영체제의 현재 화면 모드를 사용합니다. 실행 중 시스템 모드가 바뀌어도 함께 전환됩니다.
- **화이트**: 밝은 화면으로 유지합니다.
- **다크**: 어두운 화면으로 유지합니다.

선택은 즉시 모든 앱 화면에 적용되며 `data/settings.json`에 저장됩니다. 시스템 모드는 현재 색상으로 고정하지 않고 다음 실행에도 시스템 설정을 따릅니다.

## 설정

| 설정 | 동작 |
| --- | --- |
| Low | Whisper base. 빠르고 가벼운 전사 |
| Mid (기본값) | Whisper small. 속도와 정확도의 균형 |
| High | Whisper medium. 더 큰 모델로 전사, 시간과 메모리 사용량 증가 |
| 음성 언어 (기본값: 자동 감지) | 한국어·영어·일본어 등 음성 언어를 감지해 원래 언어로 전사. 파일 선택 후 작은 드롭다운에서 언어를 직접 지정할 수도 있음 |
| 타임스탬프 표시 | 전사 내용을 시간별로 표시 |
| 무음 구간 건너뛰기 | 말소리가 없는 구간을 제외하고 인식 |
| 참고 단어 | 인명·전문 용어 등 인식에 참고할 단어 입력 (최대 1,000자) |

음성 인식은 Python 라이브러리 대신 [whisper.cpp](https://github.com/ggml-org/whisper.cpp)의 `whisper-cli` 프로세스가 수행합니다. Python은 GUI와 작업 관리를 담당합니다. Apple Silicon에서는 엔진의 기본 Metal 가속을 사용합니다. MP3·M4A 등 입력은 FFmpeg로 16kHz 모노 PCM WAV로 변환한 뒤 처리하며, 임시 WAV는 작업 종료 시 삭제합니다.

처음 사용하는 GGML 모델은 한 번 다운로드됩니다. 무음 구간 건너뛰기를 사용하면 Silero VAD 모델도 다운로드합니다. 이후에는 로컬 모델을 사용하며 API 키는 필요하지 않습니다. 기존 faster-whisper 모델 캐시는 호환되지 않아 재사용하지 않으며, 기존 전사 기록은 계속 열 수 있습니다.

## 저장과 진행률

소스 실행은 기존 `data/` 저장 위치와 SQLite 형식을 유지합니다. 독립 배포본은 맥 `~/Library/Application Support/Soundnote/`, 윈도우 `%LOCALAPPDATA%\Soundnote\`를 사용합니다. 아래 경로는 소스 실행 기준입니다.

- 음성 사본: `data/uploads/`
- 작업 상태와 결과: `data/transcriptions.sqlite3`
- C++ 엔진 모델: `data/models/whisper.cpp/` (`ggml-base.bin`, `ggml-small.bin`, `ggml-medium.bin`, `ggml-silero-v5.1.2.bin`)
- 오류 로그: `data/app.log`, 실행 로그: `data/launcher.log`

음성 파일 복사와 전사는 GUI 스레드 밖에서 처리됩니다. 작업은 추가한 순서대로 하나씩 전사되며, 나머지는 대기 상태로 표시됩니다. 모델 다운로드·분석 단계는 **모델 준비 중**으로 표시됩니다. 전사 진행률은 처리한 음성 구간의 끝 시간 ÷ 전체 음성 길이를 기준으로 계산하며, 최종 완료 시 100%가 됩니다.

기록을 삭제하면 앱 내부 음성 사본과 결과가 삭제됩니다. 원래 파일은 수정하거나 삭제하지 않습니다. 파일당 최대 2GB를 지원합니다.

## 개발 및 테스트

```sh
brew install whisper.cpp ffmpeg
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
PYTHONPATH=src .venv/bin/python -m soundnote --foreground
```

터미널과 독립적으로 실행하려면 `--foreground`를 생략합니다. `--stop`으로 종료할 수 있습니다. Windows PowerShell에서는 `$env:PYTHONPATH='src'` 설정 후 `.venv\Scripts\python.exe -m soundnote`를 실행합니다. 패키지 개발 환경은 `pip install -e .`로 설치할 수도 있습니다.

```sh
.venv/bin/python scripts/test.py
# Windows: .venv\Scripts\python.exe scripts/test.py
```

GUI 테스트는 실제 Qt 위젯과 이벤트 루프를 사용합니다. 전사 작업 테스트는 제어 가능한 음성 구간 스트림으로 진행률·저장·복구를 검증합니다. C++ 엔진 연동 테스트는 가짜 CLI 프로세스로 옵션 전달, 결과 파싱, 취소와 오류 처리를 검증합니다. 실제 모델의 음성 인식 정확도와 Metal 가속은 별도 실행으로 확인해야 합니다.

실제 엔진 확인은 `whisper-cli --help`와 `ffmpeg -version`을 실행한 뒤 앱에서 짧은 음성을 전사하고 진행률, 자동 언어 감지, TXT·SRT 저장을 확인하세요. 모델 다운로드와 임시 WAV 변환에 필요한 디스크 여유 공간을 확보하세요.
