"""Run the native whisper.cpp CLI without Python inference dependencies."""

import codecs
from collections import deque
from contextlib import closing
import json
import logging
import os
from pathlib import Path
import re
import queue
import shutil
import subprocess
import tempfile
import threading
from types import SimpleNamespace
import urllib.request
import wave

from .paths import native_directory


class WhisperError(Exception):
    pass


class WhisperEngine:
    MODELS = {"low": "base", "mid": "small", "high": "medium"}
    SEGMENT = re.compile(r"^\s*\[(\d+:\d+:\d+[.,]\d+)\s*-->\s*(\d+:\d+:\d+[.,]\d+)\]\s?(.*)$")

    def __init__(self, directory, stopping=None):
        self.directory = Path(directory) / "models" / "whisper.cpp"
        self.stopping = stopping if stopping is not None else threading.Event()

    @staticmethod
    def executable(name):
        filename = name + ".exe" if os.name == "nt" and not name.endswith(".exe") else name
        native = native_directory()
        if (native / filename).is_file():
            return str(native / filename)
        if native.is_dir():
            match = next(native.rglob(filename), None)
            if match is not None:
                return str(match)
        return shutil.which(filename)

    @classmethod
    def available(cls):
        return bool(cls.executable("whisper-cli") and cls.executable("ffmpeg"))

    def check_stopping(self):
        if self.stopping.is_set():
            raise WhisperError("전사가 중단되었습니다.")

    def model_file(self, name, vad=False):
        self.check_stopping()
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / f"ggml-{name}.bin"
        if target.is_file() and target.stat().st_size:
            return target
        repository = "ggml-org/whisper-vad" if vad else "ggerganov/whisper.cpp"
        url = f"https://huggingface.co/{repository}/resolve/main/{target.name}"
        partial = None
        try:
            with urllib.request.urlopen(url, timeout=15) as response, tempfile.NamedTemporaryFile(
                    dir=self.directory, prefix=target.name, suffix=".part", delete=False) as stream:
                partial = Path(stream.name)
                expected = int(response.headers.get("Content-Length", 0))
                size = 0
                while True:
                    self.check_stopping()
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    stream.write(chunk)
                    size += len(chunk)
                if not size or (expected and size != expected):
                    raise WhisperError("모델 다운로드가 완료되지 않았습니다. 인터넷 연결을 확인하고 재시도해 주세요.")
            self.check_stopping()
            partial.replace(target)
            return target
        finally:
            if partial is not None:
                partial.unlink(missing_ok=True)

    def run(self, command, *, failure_message="whisper.cpp 전사에 실패했습니다. data/app.log를 확인해 주세요."):
        """Drain both output streams and stop children even during silent inference."""
        self.check_stopping()
        environment = os.environ.copy()
        environment.setdefault("PYTHONUTF8", "1")
        backends = native_directory() / "ggml"
        if backends.is_dir():
            environment["GGML_BACKEND_PATH"] = str(backends)
        elif native_directory().is_dir():
            environment["GGML_BACKEND_PATH"] = str(native_directory())
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, env=environment,
                                   **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
        chunks = queue.Queue(maxsize=64)
        finished = threading.Event()

        def deliver(chunk):
            while not finished.is_set():
                try:
                    chunks.put(chunk, timeout=0.1)
                    return
                except queue.Full:
                    pass

        def read_output():
            # Read output independently so cancellation stays responsive during inference.
            try:
                while not finished.is_set():
                    chunk = os.read(process.stdout.fileno(), 65536)
                    deliver(chunk)
                    if not chunk:
                        break
            except OSError as exc:
                deliver(exc)

        reader = threading.Thread(target=read_output, daemon=True, name="native-output")
        reader.start()
        recent = deque(maxlen=12)
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        pending = ""
        try:
            eof = False
            while not eof:
                self.check_stopping()
                try:
                    chunk = chunks.get(timeout=0.1)
                except queue.Empty:
                    continue
                if isinstance(chunk, OSError):
                    raise WhisperError("전사 엔진의 출력을 읽지 못했습니다.") from chunk
                eof = not chunk
                pending += decoder.decode(chunk, final=eof)
                while "\n" in pending:
                    line, pending = pending.split("\n", 1)
                    line = line.rstrip("\r")
                    recent.append(line)
                    yield line
            if pending:
                recent.append(pending)
                yield pending
            while process.poll() is None:
                self.check_stopping()
                self.stopping.wait(0.1)
            if process.returncode:
                logging.error("%s exited with %s: %s", Path(command[0]).name,
                              process.returncode, "\n".join(recent))
                raise WhisperError(failure_message)
        finally:
            finished.set()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            reader.join(timeout=1)
            process.stdout.close()

    @staticmethod
    def seconds(timestamp):
        hours, minutes, seconds = timestamp.replace(",", ".").split(":")
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)

    def transcribe(self, audio_path, model, language, options):
        cli, ffmpeg = self.executable("whisper-cli"), self.executable("ffmpeg")
        if not cli or not ffmpeg:
            raise WhisperError("whisper.cpp와 FFmpeg가 필요합니다. README.md의 설치 명령을 실행한 뒤 재시도해 주세요.")
        model_path = self.model_file(self.MODELS[model])
        vad_path = self.model_file("silero-v5.1.2", vad=True) if options["vad_filter"] else None
        # Preparation is eager so the worker receives the full audio duration.
        temporary = tempfile.TemporaryDirectory(prefix="soundnote-")
        try:
            wav_path = Path(temporary.name) / "audio.wav"
            conversion_failure = (
                "파일의 음성을 온전히 읽지 못했습니다. 원본이 끝까지 재생되는지 확인하고 "
                "정상 파일을 다시 추가해 주세요."
            )
            conversion_errors = deque(maxlen=12)
            command = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror", "-y",
                       "-i", str(Path(audio_path).resolve()), "-vn", "-ar", "16000",
                       "-ac", "1", "-c:a", "pcm_s16le", str(wav_path)]
            for line in self.run(command, failure_message=conversion_failure):
                if line.strip():
                    conversion_errors.append(line)
            if conversion_errors:
                logging.error("Audio conversion errors: %s", "\n".join(conversion_errors))
                raise WhisperError(conversion_failure)
            with wave.open(str(wav_path), "rb") as audio:
                duration = audio.getnframes() / audio.getframerate()
            output = Path(temporary.name) / "result"
            command = [cli, "--model", str(model_path), "--file", str(wav_path),
                       "--language", language, "--threads", str(min(8, os.cpu_count() or 4)),
                       "--beam-size", "5", "--output-json", "--output-file", str(output)]
            if vad_path:
                command += ["--vad", "--vad-model", str(vad_path)]
            if options["initial_prompt"]:
                command += ["--prompt", options["initial_prompt"]]
            info = SimpleNamespace(duration=duration, language=None if language == "auto" else language)
            return self.segments(command, output, temporary, info), info
        except BaseException:
            temporary.cleanup()
            raise

    def segments(self, command, output, temporary, info):
        try:
            with closing(self.run(command)) as lines:
                for line in lines:
                    match = self.SEGMENT.match(line)
                    if match:
                        start, end, text = match.groups()
                        yield SimpleNamespace(start=self.seconds(start), end=self.seconds(end), text=text)
            # JSON is authoritative; console output is only used for live updates.
            try:
                result = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
                info.language = result["result"]["language"]
                info.segments = [{"start": segment["offsets"]["from"] / 1000,
                                  "end": segment["offsets"]["to"] / 1000,
                                  "text": segment["text"].strip()}
                                 for segment in result["transcription"]]
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise WhisperError("whisper.cpp 결과를 읽지 못했습니다. 엔진 설치 상태를 확인해 주세요.") from exc
        finally:
            temporary.cleanup()
