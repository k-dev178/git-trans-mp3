# Repository Guidelines

## Project Structure & Module Organization

Soundnote (소리노트) is a Windows 10/11 x64 desktop transcription app using PySide6 and the whisper.cpp CPU CLI. Application modules live in `src/soundnote/`: `desktop.py` handles Qt UI, `appearance.py` themes, `transcription.py` storage and worker queues, `whisper_cpp.py` engine processes, and `launcher.py`, `instance.py`, `paths.py` startup and runtime files. `scripts/` contains build and test tools, `tests/` automated tests, and `docs/` documentation.

## Build, Test, and Development Commands

Use Windows x64 Python 3.10–3.13. From PowerShell at the repository root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m soundnote
.\.venv\Scripts\python.exe scripts/test.py
.\.venv\Scripts\python.exe -m pip install -r scripts/requirements-build.txt
.\.venv\Scripts\python.exe scripts/build.py
```

Use `--foreground` for attached execution and `--stop` to stop the app. Builds require CPU-only x64 `whisper-cli.exe`, `ffmpeg.exe`, required DLLs and license files in `tools/native/`; see README.md. Distribute `dist/windows/Soundnote-windows-x64.zip`. Frozen apps store data under `%LOCALAPPDATA%\Soundnote`; source checkouts use `data/`.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` for functions and variables, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants. Follow surrounding code and keep changes focused. No formatter or linter is configured. Keep visible UI text consistent with the existing Korean interface. Run file copying and transcription outside the GUI thread.

## Testing Guidelines

Run the suite with:

```sh
.\.venv\Scripts\python.exe scripts/test.py
```

Use `tests/test_<module>.py` and descriptive `test_<behavior>` methods. Tests use standard-library `unittest`, temporary storage, mocked transcription streams, and real Qt widgets. Install PySide6 to avoid skipped GUI tests. Cover relevant persistence, progress, recovery, and UI behavior; no numeric coverage threshold is configured. Recognition accuracy requires separate manual verification.

## Commit & Pull Request Guidelines

Git history is unavailable in this checkout. Use concise, imperative commit subjects, such as `Fix interrupted transcription recovery`. Describe the problem, resulting behavior, and validation in pull requests; link relevant issues and include screenshots for visible UI changes.

## Local Data & Compatibility

Keep private recordings, transcripts, model caches, logs, and virtual environments out of contributions. Preserve existing SQLite data compatibility and never modify original source audio.
