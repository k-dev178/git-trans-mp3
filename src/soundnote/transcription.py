"""Persistent local transcription jobs shared by the desktop UI and worker."""

from __future__ import annotations

from contextlib import contextmanager
import json
import logging
from pathlib import Path
import sqlite3
import threading
from datetime import datetime, timezone
import uuid

from .whisper_cpp import WhisperEngine, WhisperError

from .paths import ROOT
APP_ID = "soundnote-local"
MAX_UPLOAD = 2 * 1024**3
EXTENSIONS = {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".aac", ".opus", ".aiff", ".aif", ".mp4", ".webm"}
MODELS = {"low": "base", "mid": "small", "high": "medium"}
LANGUAGES = {"auto", "ko", "en", "ja", "zh", "es", "fr", "de", "it", "pt", "ru", "vi", "th", "ar"}
ACTIVE = {"queued", "preparing", "transcribing"}
LOG = logging.getLogger("soundnote")


def now():
    return datetime.now(timezone.utc).isoformat()


class AppError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.uploads = self.directory / "uploads"
        self.uploads.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "transcriptions.sqlite3"
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, filename TEXT NOT NULL, size INTEGER NOT NULL,
                model TEXT NOT NULL, language TEXT NOT NULL, status TEXT NOT NULL,
                progress REAL NOT NULL DEFAULT 0, duration REAL NOT NULL DEFAULT 0,
                processed REAL NOT NULL DEFAULT 0, detected_language TEXT,
                text TEXT NOT NULL DEFAULT '', segments TEXT NOT NULL DEFAULT '[]',
                error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                audio_path TEXT NOT NULL, options TEXT NOT NULL DEFAULT '{}'
            )""")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def decode(row, details=False):
        result = dict(row)
        result.pop("audio_path")
        result["options"] = json.loads(result["options"])
        segments = result.pop("segments")
        if details:
            result["segments"] = json.loads(segments)
        else:
            result["preview"] = result.pop("text")[:160]
        return result

    def list(self):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        return [self.decode(row) for row in rows]

    def raw(self, job_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise AppError("전사 기록을 찾을 수 없습니다.", 404)
        return dict(row)

    def get(self, job_id):
        return self.decode(self.raw(job_id), details=True)

    def create(self, job_id, filename, size, model, language, audio_path, options):
        stamp = now()
        with self.connect() as db:
            db.execute("""INSERT INTO jobs
                (id, filename, size, model, language, status, created_at, updated_at, audio_path, options)
                VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?)""",
                (job_id, filename, size, model, language, stamp, stamp, str(audio_path), json.dumps(options)))
        return self.get(job_id)

    @staticmethod
    def validate_file(source):
        source = Path(source)
        if not source.is_file():
            raise AppError("읽을 수 있는 음성 파일을 선택해 주세요.")
        if source.suffix.lower() not in EXTENSIONS:
            raise AppError("MP3, M4A, WAV 등 지원되는 음성 파일을 선택해 주세요.")
        size = source.stat().st_size
        if size <= 0:
            raise AppError("비어 있는 파일은 전사할 수 없습니다.")
        if size > MAX_UPLOAD:
            raise AppError("최대 2GB까지 추가할 수 있습니다.")
        return size

    def add_file(self, source, model="mid", language="auto", options=None, progress=None, stop=None):
        source = Path(source)
        size = self.validate_file(source)
        if model not in MODELS or language not in LANGUAGES:
            raise AppError("모델 또는 언어 설정을 확인해 주세요.")
        options = {"timestamps": True, "vad_filter": True, "initial_prompt": "", **(options or {})}
        if not isinstance(options["timestamps"], bool) or not isinstance(options["vad_filter"], bool):
            raise AppError("세부 설정을 확인해 주세요.")
        if not isinstance(options["initial_prompt"], str) or len(options["initial_prompt"]) > 1000:
            raise AppError("참고 단어는 1,000자 이내로 입력해 주세요.")
        options["initial_prompt"] = options["initial_prompt"].strip()
        job_id = uuid.uuid4().hex
        target = self.uploads / (job_id + source.suffix.lower())
        partial = self.uploads / (job_id + ".part")
        copied = 0
        try:
            with source.open("rb") as original, partial.open("wb") as destination:
                while chunk := original.read(1024 * 1024):
                    if stop is not None and stop.is_set():
                        raise AppError("파일 추가가 중단되었습니다.")
                    copied += len(chunk)
                    if copied > size:
                        raise AppError("파일이 복사 중에 변경되었습니다. 다시 추가해 주세요.")
                    destination.write(chunk)
                    if progress:
                        progress(round(copied / size * 100))
            if copied != size:
                raise AppError("파일이 복사 중에 변경되었습니다. 다시 추가해 주세요.")
            partial.replace(target)
            return self.create(job_id, source.name, size, model, language, target, options)
        except Exception:
            partial.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
            raise

    def update(self, job_id, **fields):
        allowed = {"status", "progress", "duration", "processed", "detected_language", "text", "segments", "error"}
        if not fields or not set(fields) <= allowed:
            raise ValueError("Invalid job update")
        fields["updated_at"] = now()
        sql = ", ".join(f"{key} = ?" for key in fields)
        with self.connect() as db:
            db.execute(f"UPDATE jobs SET {sql} WHERE id = ?", (*fields.values(), job_id))

    def recover(self):
        # Original audio is retained so interrupted work can be run again.
        with self.connect() as db:
            db.execute("""UPDATE jobs SET status = 'queued', progress = 0, processed = 0,
                text = '', segments = '[]', error = NULL, updated_at = ?
                WHERE status IN ('preparing', 'transcribing')""", (now(),))
        for partial in self.uploads.glob("*.part"):
            partial.unlink(missing_ok=True)

    def next_queued(self):
        with self.connect() as db:
            row = db.execute("SELECT id FROM jobs WHERE status = 'queued' ORDER BY created_at LIMIT 1").fetchone()
        return row["id"] if row else None

    def retry(self, job_id):
        with self.connect() as db:
            row = db.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                raise AppError("전사 기록을 찾을 수 없습니다.", 404)
            if row["status"] != "failed":
                raise AppError("실패한 작업만 다시 시작할 수 있습니다.", 409)
            db.execute("""UPDATE jobs SET status = 'queued', progress = 0, processed = 0,
                duration = 0, detected_language = NULL, text = '', segments = '[]',
                error = NULL, updated_at = ? WHERE id = ?""", (now(), job_id))
        return self.get(job_id)

    def delete(self, job_id):
        with self.connect() as db:
            row = db.execute("SELECT status, audio_path FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                raise AppError("전사 기록을 찾을 수 없습니다.", 404)
            if row["status"] in ACTIVE:
                raise AppError("진행 중인 전사는 완료된 후 삭제할 수 있습니다.", 409)
            # Unlink before removing the row so a filesystem error leaves a retryable record.
            Path(row["audio_path"]).unlink(missing_ok=True)
            db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))


class Worker:
    def __init__(self, store, engine=None):
        self.store = store
        self.stopping = threading.Event()
        self.engine = engine if engine is not None else WhisperEngine(store.directory, self.stopping)
        self.wakeup = threading.Event()
        self.thread = threading.Thread(target=self.run, name="transcription-worker", daemon=True)

    def start(self):
        self.store.recover()
        self.thread.start()

    def stop(self):
        self.stopping.set()
        self.wakeup.set()
        if self.thread.is_alive():
            self.thread.join(timeout=3)

    def run(self):
        while not self.stopping.is_set():
            self.wakeup.clear()
            job_id = self.store.next_queued()
            if job_id:
                self.process(job_id)
            else:
                self.wakeup.wait(1)

    def process(self, job_id):
        segments = None
        try:
            job = self.store.raw(job_id)
            self.store.update(job_id, status="preparing", progress=0)
            segments, info = self.engine.transcribe(Path(job["audio_path"]),
                job["model"], job["language"], json.loads(job["options"]))
            duration = max(0.0, float(info.duration))
            self.store.update(job_id, status="transcribing", duration=duration, detected_language=info.language)
            captured = []
            previous_progress = 0
            for segment in segments:
                if self.stopping.is_set():
                    return  # startup recovery requeues this persisted job
                captured.append({"start": float(segment.start), "end": float(segment.end), "text": segment.text.strip()})
                processed = min(duration, max(0, float(segment.end)))
                progress = max(previous_progress, min(99, round(processed / duration * 100, 1))) if duration else 0
                previous_progress = progress
                self.store.update(job_id, progress=progress, processed=processed,
                    text="\n".join(s["text"] for s in captured), segments=json.dumps(captured, ensure_ascii=False))
            if not self.stopping.is_set():
                captured = getattr(info, "segments", captured)
                self.store.update(job_id, status="completed", progress=100, processed=duration,
                    detected_language=info.language, text="\n".join(s["text"] for s in captured),
                    segments=json.dumps(captured, ensure_ascii=False))
        except Exception as exc:
            if self.stopping.is_set():
                return  # retain interrupted state for startup recovery
            LOG.exception("Transcription failed: %s", job_id)
            if isinstance(exc, (AppError, WhisperError)):
                message = str(exc)
            elif isinstance(exc, (ConnectionError, TimeoutError, OSError)):
                message = "파일이나 모델을 불러오지 못했습니다. 원본 파일과 인터넷 연결을 확인한 뒤 재시도해 주세요."
            else:
                message = "전사에 실패했습니다. 올바른 음성 파일인지 확인한 뒤 재시도해 주세요. 자세한 내용은 data/app.log에서 확인할 수 있습니다."
            self.store.update(job_id, status="failed", error=message)
        finally:
            if hasattr(segments, "close"):
                segments.close()


def subtitle_time(seconds):
    millis = max(0, round(seconds * 1000))
    hours, rest = divmod(millis, 3600000)
    minutes, rest = divmod(rest, 60000)
    secs, ms = divmod(rest, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"


def export_text(job, format_name):
    if format_name == "srt":
        return "\n\n".join(f"{index}\n{subtitle_time(s['start'])} --> {subtitle_time(s['end'])}\n{s['text']}"
            for index, s in enumerate(job["segments"], 1)) + "\n"
    return job["text"] + "\n"
