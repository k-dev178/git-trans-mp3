"""Create a standalone macOS app and ZIP."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from soundnote.whisper_cpp import WhisperEngine


def build_command(executables, extra_binaries=(), extra_data=()):
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
               "--windowed", "--onedir", "--name", "Soundnote", "--paths", str(ROOT / "src"),
               "--distpath", str(ROOT / "dist/macos"),
               "--workpath", str(ROOT / "build/macos"), "--specpath", str(ROOT / "build")]
    for executable in executables:
        command += ["--add-binary", f"{executable}{os.pathsep}native"]
    for source, destination in extra_binaries:
        command += ["--add-binary", f"{source}{os.pathsep}{destination}"]
    for source, destination in extra_data:
        command += ["--add-data", f"{source}{os.pathsep}{destination}"]
    command += ["--add-data", f"{ROOT / 'docs/THIRD_PARTY.md'}{os.pathsep}licenses"]
    command += ["--icon", str(ROOT / "assets/macos/Soundnote.icns"),
                "--osx-bundle-identifier", "local.soundnote.desktop"]
    command.append(str(ROOT / "scripts/app_entry.py"))
    return command


def native_files(executables):
    binaries, data = [], []
    # Modern Homebrew ggml loads CPU/Metal backend plugins at runtime;
    # dependency analysis alone cannot discover dlopen() modules.
    brew = shutil.which("brew")
    if brew:
        result = subprocess.run([brew, "--prefix", "ggml"], capture_output=True, text=True)
        if result.returncode == 0:
            prefix = Path(result.stdout.strip())
            for path in (prefix / "libexec").glob("*"):
                if path.suffix in {".so", ".dylib"}:
                    binaries.append((str(path), "native/ggml"))
                elif path.is_file():
                    data.append((str(path), "native/ggml"))
    # Preserve license notices shipped with Homebrew tools.
    for executable in executables:
        prefix = Path(executable).resolve().parent.parent
        for path in prefix.glob("*LICENSE*"):
            if path.is_file():
                data.append((str(path), f"licenses/{prefix.parent.name}"))
    return binaries, data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true", help="Show resolved build inputs without building")
    args = parser.parse_args()
    if sys.platform != "darwin":
        sys.exit("Build on macOS.")
    executables = [WhisperEngine.executable(name) for name in ("whisper-cli", "ffmpeg")]
    if not all(executables):
        sys.exit("whisper.cpp and FFmpeg are required. See the installation commands in README.md.")
    binaries, data = native_files(executables)
    command = build_command(executables, binaries, data)
    if args.plan:
        print(json.dumps({"target": "macos", "architecture": platform.machine(), "command": command},
                         ensure_ascii=False, indent=2))
        return
    if importlib.util.find_spec("PyInstaller") is None:
        sys.exit("PyInstaller is required. Run .venv/bin/python -m pip install -r scripts/requirements-build.txt")
    environment = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(ROOT / "build/pyinstaller-cache"))
    subprocess.run(command, cwd=ROOT, env=environment, check=True)
    destination = ROOT / "dist/macos"
    app = destination / "Soundnote.app"
    if not app.is_dir():
        raise RuntimeError("PyInstaller did not create Soundnote.app")
    archive = destination / f"Soundnote-macos-{platform.machine()}.zip"
    # ditto preserves the bundle's executable bits, symlinks and resources.
    subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app), str(archive)], check=True)
    shutil.rmtree(destination / "Soundnote", ignore_errors=True)
    print(f"Distribution ready: {archive}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        sys.exit(f"Build failed: {exc}")
