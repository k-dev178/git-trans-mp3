# Repository Guidelines

## Project Structure & Module Organization

Soundnote (소리노트) is a macOS desktop transcription app using PySide6 and faster-whisper. Python modules live at the repository root:

- `app.py`: application entry point; `launcher.py`: detached launch, single-instance handling, and shutdown.
- `desktop.py`: Qt windows and interaction; `appearance.py`: themes and saved appearance preferences.
- `transcription.py`: SQLite storage, file imports, transcription engine, worker queue, and exports.
- `qt_bootstrap.py` and `migrate_legacy.py`: runtime discovery and legacy-process handling.

`tests/` contains automated tests; `preview/` contains GUI screenshots. `소리노트.app/` is a launcher bundle that must remain inside the project directory. `data/` holds runtime files, uploaded audio, results, and downloaded models.

## Build, Test, and Development Commands

Use Python 3.10–3.13. From the repository root:

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

These commands create the environment, install dependencies, and launch the GUI. Use `.venv/bin/python launcher.py` for detached execution and `.venv/bin/python launcher.py --stop` to stop it. The macOS `설치.command`, `실행.command`, and `종료.command` scripts provide installation, launch, and shutdown shortcuts. No separate build step is configured.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` for functions and variables, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants. Follow surrounding code and keep changes focused. No formatter or linter is configured. Keep visible UI text consistent with the existing Korean interface. Run file copying and transcription outside the GUI thread.

## Testing Guidelines

Run the suite with:

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v
```

Use `tests/test_<module>.py` and descriptive `test_<behavior>` methods. Tests use standard-library `unittest`, temporary storage, mocked transcription streams, and real Qt widgets. Install PySide6 to avoid skipped GUI tests. Cover relevant persistence, progress, recovery, and UI behavior; no numeric coverage threshold is configured. Recognition accuracy requires separate manual verification.

## Commit & Pull Request Guidelines

Git history is unavailable in this checkout. Use concise, imperative commit subjects, such as `Fix interrupted transcription recovery`. Describe the problem, resulting behavior, and validation in pull requests; link relevant issues and include screenshots for visible UI changes.

## Local Data & Compatibility

Keep private recordings, transcripts, model caches, logs, and virtual environments out of contributions. Preserve existing SQLite data compatibility and never modify original source audio.
