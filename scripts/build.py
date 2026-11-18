"""Create a standalone Windows x64 app and ZIP from tools/native inputs."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "tools/native"
WINDOWS_ICON = ROOT / "assets/windows/Soundnote.ico"


def build_command(executables, extra_binaries=(), extra_data=()):
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
               "--windowed", "--onedir", "--name", "Soundnote", "--icon", str(WINDOWS_ICON),
               "--paths", str(ROOT / "src"),
               "--distpath", str(ROOT / "dist/windows"),
               "--workpath", str(ROOT / "build/windows"), "--specpath", str(ROOT / "build")]
    for executable in executables:
        command += ["--add-binary", f"{executable}{os.pathsep}native"]
    for source, destination in extra_binaries:
        command += ["--add-binary", f"{source}{os.pathsep}{destination}"]
    for source, destination in extra_data:
        command += ["--add-data", f"{source}{os.pathsep}{destination}"]
    command += ["--add-data", f"{ROOT / 'docs/THIRD_PARTY.md'}{os.pathsep}licenses"]
    command.append(str(ROOT / "scripts/app_entry.py"))
    return command


def validate_x64(path):
    """Reject non-PE or non-x64 inputs before starting PyInstaller."""
    try:
        with Path(path).open("rb") as stream:
            if stream.read(2) != b"MZ":
                raise ValueError
            stream.seek(0x3c)
            offset, = struct.unpack("<I", stream.read(4))
            stream.seek(offset)
            if stream.read(4) != b"PE\0\0" or stream.read(2) != b"\x64\x86":
                raise ValueError
    except (OSError, ValueError, struct.error) as exc:
        raise RuntimeError(f"A Windows x64 executable or DLL is required: {path}") from exc


def native_files(directory=NATIVE):
    directory = Path(directory)
    executables = [directory / name for name in ("whisper-cli.exe", "ffmpeg.exe")]
    for executable in executables:
        if not executable.is_file():
            raise RuntimeError(f"Required tool is missing: {executable}. See README.md.")
    # Keep each runtime DLL next to the executables that load it.
    binaries = [(str(path), "native") for path in sorted(directory.iterdir())
                if path.is_file() and path.suffix.lower() == ".dll"]
    for path in [*executables, *(Path(source) for source, _ in binaries)]:
        validate_x64(path)
    data = []
    for component in ("whisper.cpp", "ffmpeg"):
        notices = directory / "licenses" / component
        if not notices.is_dir() or not any(path.is_file() for path in notices.rglob("*")):
            raise RuntimeError(f"Native license files are required in {notices}")
    for path in sorted((directory / "licenses").rglob("*")):
        if path.is_file():
            destination = Path("licenses/native") / path.parent.relative_to(directory / "licenses")
            data.append((str(path), destination.as_posix()))
    return [str(path) for path in executables], binaries, data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true", help="Validate and show inputs without building")
    args = parser.parse_args()
    executables, binaries, data = native_files()
    command = build_command(executables, binaries, data)
    if args.plan:
        print(json.dumps({"target": "windows", "architecture": "x64", "command": command},
                         ensure_ascii=False, indent=2))
        return
    if sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64"} or struct.calcsize("P") != 8:
        sys.exit("Build with x64 Python on Windows x64.")
    if importlib.util.find_spec("PyInstaller") is None:
        sys.exit("PyInstaller is required. Run python -m pip install -r scripts/requirements-build.txt")
    environment = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(ROOT / "build/pyinstaller-cache"))
    subprocess.run(command, cwd=ROOT, env=environment, check=True)
    destination = ROOT / "dist/windows"
    app = destination / "Soundnote"
    if not (app / "Soundnote.exe").is_file():
        raise RuntimeError("PyInstaller did not create Soundnote/Soundnote.exe")
    # Fail the distribution if a required non-system DLL cannot be loaded.
    bundled_native = app / "_internal/native"
    probe_environment = dict(os.environ, GGML_BACKEND_PATH=str(bundled_native))
    system_root = Path(os.environ.get("SystemRoot", "C:/Windows"))
    probe_environment["PATH"] = os.pathsep.join([str(bundled_native), str(system_root / "System32"), str(system_root)])
    for executable in ("whisper-cli.exe", "ffmpeg.exe"):
        binary = bundled_native / executable
        subprocess.run([str(binary), "--help" if executable == "whisper-cli.exe" else "-version"],
                       cwd=binary.parent, env=probe_environment, check=True, timeout=30)
    archive = shutil.make_archive(str(destination / "Soundnote-windows-x64"), "zip",
                                  root_dir=destination, base_dir="Soundnote")
    print(f"Distribution ready: {archive}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        sys.exit(f"Build failed: {exc}")
