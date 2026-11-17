# Included components

Soundnote uses Python, PySide6/Qt, whisper.cpp, GGML and FFmpeg. Standalone
builds include the required runtimes and native executables; model weights
are downloaded separately on first use. Private audio and transcripts are
never included by the build script.

- Python: https://www.python.org/ — PSF License.
- PySide6 and Qt: https://www.qt.io/qt-for-python — LGPL/GPL/commercial licenses,
  depending on the included module.
- whisper.cpp: https://github.com/ggml-org/whisper.cpp — MIT License.
- GGML: https://github.com/ggml-org/ggml — MIT License.
- FFmpeg: https://ffmpeg.org/ — LGPL/GPL, depending on build configuration.

The Windows build script preserves all notices from tools/native/licenses.
Supply the notices for the exact whisper.cpp, GGML, FFmpeg and runtime DLL builds
under the whisper.cpp and ffmpeg component directories before building.
Check the licenses of the exact binaries before
redistributing them; retain notices and meet applicable source requirements.
