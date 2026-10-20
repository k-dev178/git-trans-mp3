"""Install local Windows x64 CLI tools; macOS uses Homebrew."""

import hashlib
import io
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tools/native"
WHISPER_URL = "https://github.com/ggml-org/whisper.cpp/releases/download/b5454/whisper-bin-x64.zip"
WHISPER_SHA256 = "6ba69e3482d7826214f90a6a9c84ca07782aec1e1d0c6a7c30c994fd5d816ccb"
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"


def download(url):
    print(f"Downloading {url}", flush=True)
    request = urllib.request.Request(url, headers={"User-Agent": "Soundnote-Setup/2.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def install_archive(url, destination, checksum):
    payload = download(url)
    if hashlib.sha256(payload).hexdigest() != checksum.lower():
        raise RuntimeError(f"Download checksum mismatch: {url}. Retry installation.")
    # Extract to a sibling temp directory so a failed install can be retried.
    with tempfile.TemporaryDirectory(dir=TARGET) as temporary:
        temporary = Path(temporary)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for item in archive.infolist():
                resolved = (temporary / item.filename).resolve()
                if not resolved.is_relative_to(temporary.resolve()):
                    raise RuntimeError("Unsafe archive path")
            archive.extractall(temporary)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(temporary, destination)


def find_executable(name):
    local = next(TARGET.rglob(name + ".exe"), None) if TARGET.exists() else None
    return str(local) if local else shutil.which(name)


def main():
    if sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64"}:
        sys.exit("This installer requires Windows x64. On macOS, use the Mac install command.")
    TARGET.mkdir(parents=True, exist_ok=True)
    if not find_executable("whisper-cli"):
        install_archive(WHISPER_URL, TARGET / "whisper", WHISPER_SHA256)
    if not find_executable("ffmpeg"):
        checksum = download(FFMPEG_URL + ".sha256").decode("ascii").split()[0]
        install_archive(FFMPEG_URL, TARGET / "ffmpeg", checksum)
    for name, argument in [("whisper-cli", "--help"), ("ffmpeg", "-version")]:
        executable = find_executable(name)
        if not executable:
            raise RuntimeError(f"{name}.exe is missing after installation")
        subprocess.run([executable, argument], check=True, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=0x08000000)
    print("whisper.cpp and FFmpeg are ready.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, zipfile.BadZipFile) as exc:
        sys.exit(f"Native tool installation failed: {exc}")
