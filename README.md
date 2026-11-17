# 소리노트 Windows

음성 파일을 텍스트로 전사하는 Windows 10/11 x64 데스크톱 프로그램입니다. 한국어 Qt 화면과 whisper.cpp CPU 엔진을 사용합니다. API 키나 GPU는 필요하지 않습니다.

## 배포본 실행

`Soundnote-windows-x64.zip`을 폴더 전체에 압축 해제한 뒤 `Soundnote/Soundnote.exe`를 실행하세요. `_internal` 폴더도 함께 유지해야 합니다. Python·Qt·whisper.cpp·FFmpeg는 배포본에 포함됩니다.

첫 전사에서는 모델을 인터넷으로 다운로드합니다. 이후 같은 모델의 전사는 로컬에서 처리합니다. 설치 프로그램·자동 업데이트·코드 서명은 제공하지 않습니다.

1. **+**를 누르고 MP3·M4A 등 파일을 선택하거나 끌어다 놓습니다.
2. 모델·언어·설정을 고르고 **확인 · 전사 시작**을 누릅니다.
3. 완료한 기록을 열어 복사하거나 TXT·SRT로 저장합니다. 실패한 작업은 재시도할 수 있습니다.

## 개발 환경 설치

Windows x64용 Python 3.10~3.13을 설치하세요. 다음 명령은 프로젝트 루트의 PowerShell에서 실행합니다.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m soundnote
```

개발 실행에도 Windows x64용 `whisper-cli.exe`와 `ffmpeg.exe`가 필요합니다. `tools/native/`에 필요한 DLL과 함께 두거나 PATH에 등록하세요. 배포 빌드는 반드시 `tools/native/`의 도구를 사용합니다.

로그를 보며 실행하려면 `--foreground`, 종료하려면 `--stop`을 사용합니다.

```powershell
.\.venv\Scripts\python.exe -m soundnote --foreground
.\.venv\Scripts\python.exe -m soundnote --stop
```

## Windows 배포본 빌드

Windows x64 환경과 x64 Python에서 빌드합니다. 네이티브 도구는 빌드 스크립트가 다운로드하지 않습니다. CPU용 whisper.cpp와 FFmpeg의 신뢰할 수 있는 Windows x64 빌드를 준비하세요.

```text
tools/native/
  whisper-cli.exe
  ffmpeg.exe
  *.dll
  licenses/
    whisper.cpp/  엔진·GGML 및 관련 구성요소의 라이선스
    ffmpeg/       사용한 FFmpeg 빌드의 라이선스·배포 고지
```

DLL은 하위 폴더 대신 실행 파일 옆에 두세요. 엔진 빌드에서 사용하는 whisper·GGML·OpenMP 등의 DLL과 FFmpeg DLL을 빠짐없이 포함해야 합니다. 정적 빌드는 별도 DLL이 필요하지 않을 수 있습니다. 배포하려는 PC의 CPU 명령어와 호환되는 엔진을 사용하세요. CUDA·Vulkan·Metal 전용 빌드는 사용하지 않습니다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r scripts/requirements-build.txt
.\.venv\Scripts\python.exe scripts/build.py --plan
.\.venv\Scripts\python.exe scripts/build.py
```

빌드는 도구와 DLL의 PE x64 형식, 구성요소별 라이선스 파일 존재를 검사합니다. PyInstaller로 묶은 뒤 동봉 도구를 실행해 누락된 런타임 의존성을 확인합니다. `--plan`은 입력만 검사하며 다른 OS에서도 실행할 수 있습니다.

결과는 `dist/windows/Soundnote/`와 `dist/windows/Soundnote-windows-x64.zip`입니다. 개인 녹음·DB·설정·모델 캐시는 포함하지 않습니다. 구성요소의 배포 조건은 [THIRD_PARTY.md](docs/THIRD_PARTY.md)를 참고하세요.

## 백그라운드 동작과 단축키

- 창을 닫으면 숨겨지고 전사는 계속됩니다. 시스템 트레이 아이콘으로 다시 열 수 있습니다.
- 트레이 메뉴에서 **전사 목록 열기**, **새 전사**, **설정…**, **소리노트 종료**를 선택합니다.
- 앱을 다시 실행하면 기존 창을 엽니다. 완전히 종료하려면 메뉴의 **소리노트 종료**를 사용합니다.
- 새 전사: `Ctrl+N`, 설정: `Ctrl+,`, 종료: `Ctrl+Q`, 파일 추가 화면에서 돌아가기: `Esc`.
- 컴퓨터가 절전 상태이면 처리도 멈춥니다. 종료로 중단된 작업은 다음 실행에서 처음부터 다시 처리됩니다.

## 전사와 화면 설정

Low는 Whisper base, Mid(기본값)는 small, High는 medium 모델입니다. 큰 모델일수록 메모리와 처리 시간이 더 필요합니다. 언어 자동 감지 또는 직접 지정, 타임스탬프 표시, 무음 구간 건너뛰기, 참고 단어(최대 1,000자)를 지원합니다.

FFmpeg로 입력을 16kHz 모노 PCM WAV로 변환한 뒤 전사하며 임시 WAV는 작업 종료 시 삭제합니다. 무음 건너뛰기는 별도의 Silero VAD 모델을 처음 한 번 다운로드합니다.

설정에서 시스템 화면 모드(기본값)·화이트·다크를 선택할 수 있습니다. 선택은 즉시 적용되고 저장됩니다.

## 데이터 저장

배포본은 `%LOCALAPPDATA%\Soundnote`, 소스 실행은 프로젝트의 `data/`를 사용합니다. ZIP을 교체하거나 앱 폴더를 옮겨도 배포본의 기록은 유지됩니다. `SOUNDNOTE_DATA_DIR` 환경변수 또는 `--data-dir`로 다른 저장 폴더를 지정할 수 있습니다.

- `uploads/`: 원본을 보존한 음성 사본
- `transcriptions.sqlite3`: 작업 상태와 결과
- `models/whisper.cpp/`: GGML 전사 모델·VAD 모델
- `settings.json`: 화면 설정
- `app.log`, `launcher.log`: 오류·실행 로그

SQLite 형식은 기존 기록과 호환됩니다. 음성 사본의 경로는 DB에 절대 경로로 저장되므로 macOS 데이터를 Windows로 옮기는 이관 기능은 제공하지 않습니다. 기존 faster-whisper 모델 캐시는 재사용하지 않습니다.

파일 복사와 전사는 GUI 스레드 밖에서 수행합니다. 작업은 추가 순서대로 하나씩 처리하며 파일당 최대 2GB를 지원합니다. 기록 삭제는 앱 내부 사본과 결과만 삭제하고 원본 음성은 수정하지 않습니다.

## 개발 및 테스트

```powershell
.\.venv\Scripts\python.exe scripts/test.py
```

`src/soundnote/`에 GUI·저장소·엔진·실행 코드가 있고, `scripts/`에 빌드·테스트 도구, `tests/`에 unittest 테스트가 있습니다. GUI 테스트는 Qt 위젯을 사용하며 엔진 테스트는 가짜 CLI로 옵션·진행률·취소·결과 파싱을 확인합니다.

배포 전 Python과 개발 도구가 없는 Windows 10/11 x64 PC에서 압축 해제·실행, 한글과 공백 경로, 첫 모델 다운로드, 실제 전사, TXT·SRT 저장, 트레이 복원, 중복 실행, 종료 및 중단 작업 복구를 확인하세요. 인식 정확도와 실제 Windows EXE 동작은 별도 검증이 필요합니다.
