import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from soundnote.transcription import Store, Worker, export_text
from soundnote.whisper_cpp import WhisperEngine, WhisperError


class WhisperCppTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.engine = WhisperEngine(self.root)
        self.source = self.root / "회의 음성.m4a"
        self.source.write_bytes(b"original audio")
        self.arguments = self.root / "arguments.json"
        self.options = {"vad_filter": True, "timestamps": False, "initial_prompt": "고유명사 $(echo test)"}
        self.ffmpeg = self.executable("fake ffmpeg", '''
import sys, wave
with wave.open(sys.argv[-1], "wb") as output:
    output.setnchannels(1)
    output.setsampwidth(2)
    output.setframerate(16000)
    output.writeframes(b"\\0\\0" * 160000)
''')
        self.cli = self.executable("fake whisper-cli", f'''
import json, sys
from pathlib import Path
Path({str(self.arguments)!r}).write_text(json.dumps(sys.argv[1:]))
print("whisper_init: loading model", file=sys.stderr, flush=True)
print("[00:00:00.000 --> 00:00:02.500] 첫 문장", flush=True)
print("[00:00:02.500 --> 00:00:10.000] 다음 문장", flush=True)
result = {{"result": {{"language": "ko"}}, "transcription": [
    {{"offsets": {{"from": 0, "to": 2500}}, "text": " 첫 문장 "}},
    {{"offsets": {{"from": 2500, "to": 10000}}, "text": " 다음 문장 "}}]}}
Path(sys.argv[sys.argv.index("--output-file") + 1] + ".json").write_text(json.dumps(result))
''')
        self.addCleanup(patch.stopall)
        patch.object(self.engine, "executable", side_effect=lambda name: str(
            self.cli if name == "whisper-cli" else self.ffmpeg)).start()
        self.models = patch.object(self.engine, "model_file", side_effect=lambda name, **kwargs:
                                  self.root / f"ggml-{name}.bin").start()
        native_run = self.engine.run
        patch.object(self.engine, "run", side_effect=lambda command: native_run(
            [sys.executable, *command] if command[0] in {str(self.cli), str(self.ffmpeg)} else command)).start()

    def executable(self, name, source):
        target = self.root / (name + ".py")
        target.write_text(f"#!{sys.executable}\n" + source, encoding="utf-8")
        target.chmod(0o755)
        return target

    def test_native_process_streams_segments_and_preserves_options(self):
        segments, info = self.engine.transcribe(self.source, "high", "auto", self.options)
        self.assertEqual(info.duration, 10)
        self.assertIsNone(info.language)
        self.assertEqual([(s.start, s.end, s.text) for s in segments],
                         [(0, 2.5, "첫 문장"), (2.5, 10, "다음 문장")])
        self.assertEqual(info.language, "ko")
        self.assertEqual(info.segments[-1], {"start": 2.5, "end": 10, "text": "다음 문장"})
        args = json.loads(self.arguments.read_text())
        self.assertEqual(args[args.index("--language") + 1], "auto")
        self.assertEqual(args[args.index("--prompt") + 1], self.options["initial_prompt"])
        self.assertIn("--vad", args)
        self.assertNotIn("--no-timestamps", args)  # UI setting must not remove SRT timestamps.
        self.assertEqual(Path(args[args.index("--model") + 1]).name, "ggml-medium.bin")
        self.assertFalse(Path(args[args.index("--file") + 1]).exists())
        self.assertEqual(self.source.read_bytes(), b"original audio")

    def test_worker_persists_native_json_and_auto_language(self):
        store = Store(self.root / "jobs")
        job = store.add_file(self.source)
        Worker(store, self.engine).process(job["id"])
        result = store.get(job["id"])
        self.assertEqual((result["status"], result["progress"], result["detected_language"]),
                         ("completed", 100, "ko"))
        self.assertEqual(result["text"], "첫 문장\n다음 문장")
        self.assertEqual(result["segments"][-1]["end"], 10)

    def test_vad_and_prompt_can_be_disabled(self):
        options = {**self.options, "vad_filter": False, "initial_prompt": ""}
        segments, _ = self.engine.transcribe(self.source, "low", "ko", options)
        list(segments)
        self.models.assert_called_once_with("base")
        args = json.loads(self.arguments.read_text())
        self.assertNotIn("--vad", args)
        self.assertNotIn("--prompt", args)
        self.assertEqual(args[args.index("--language") + 1], "ko")

    def test_foreign_auto_results_keep_original_language_and_exports(self):
        store = Store(self.root / "jobs")
        for language, text in [("en", "Hello, this is a meeting."), ("ja", "こんにちは。会議を始めます。"),
                               ("es", "Buenos días. Vamos a empezar."), ("ar", "مرحبا بكم")]:
            with self.subTest(language=language):
                result = {"result": {"language": language}, "transcription": [
                    {"offsets": {"from": 0, "to": 2500}, "text": text}]}
                self.cli.write_text(f'''#!{sys.executable}
import sys
from pathlib import Path
Path({str(self.arguments)!r}).write_text(__import__('json').dumps(sys.argv[1:]))
Path(sys.argv[sys.argv.index('--output-file') + 1] + '.json').write_text({json.dumps(result)!r})
''', encoding="utf-8")
                job = store.add_file(self.source)
                Worker(store, self.engine).process(job["id"])
                saved = store.get(job["id"])
                self.assertEqual((saved["status"], saved["language"], saved["detected_language"]),
                                 ("completed", "auto", language))
                self.assertEqual(saved["text"], text)
                self.assertEqual(export_text(saved, "txt"), text + "\n")
                self.assertIn(text, export_text(saved, "srt"))
                args = json.loads(self.arguments.read_text())
                self.assertEqual(args[args.index("--language") + 1], "auto")
                self.assertNotIn("--translate", args)
                self.assertEqual(Path(args[args.index("--model") + 1]).name, "ggml-small.bin")

    def test_missing_native_dependencies_explains_installation(self):
        with patch.object(self.engine, "executable", return_value=None):
            with self.assertRaisesRegex(WhisperError, "README.md"):
                self.engine.transcribe(self.source, "mid", "auto", self.options)

    def test_success_exit_without_result_is_failure(self):
        self.cli.write_text(f"#!{sys.executable}\n", encoding="utf-8")
        segments, _ = self.engine.transcribe(self.source, "mid", "auto", self.options)
        with self.assertRaisesRegex(WhisperError, "결과"):
            list(segments)

    def test_native_failure_is_persisted_as_retryable_job(self):
        self.cli.write_text(f"#!{sys.executable}\nimport sys\nsys.exit(2)\n", encoding="utf-8")
        store = Store(self.root / "jobs")
        job = store.add_file(self.source)
        with self.assertLogs(level="ERROR"):
            Worker(store, self.engine).process(job["id"])
        failed = store.get(job["id"])
        self.assertEqual(failed["status"], "failed")
        self.assertIn("whisper.cpp", failed["error"])
        self.assertEqual(store.retry(job["id"])["status"], "queued")

    def test_empty_native_result_completes_without_invented_text(self):
        self.cli.write_text(f'''#!{sys.executable}
import json, sys
from pathlib import Path
Path(sys.argv[sys.argv.index("--output-file") + 1] + ".json").write_text(
    json.dumps({{"result": {{"language": "ko"}}, "transcription": []}}))
''', encoding="utf-8")
        store = Store(self.root / "jobs")
        job = store.add_file(self.source)
        Worker(store, self.engine).process(job["id"])
        result = store.get(job["id"])
        self.assertEqual((result["status"], result["text"], result["segments"]), ("completed", "", []))

    def test_worker_shutdown_preserves_interrupted_job_for_recovery(self):
        self.cli.write_text(f'''#!{sys.executable}
import time
print("[00:00:00.000 --> 00:00:02.500] 첫 문장", flush=True)
time.sleep(60)
''', encoding="utf-8")
        store = Store(self.root / "jobs")
        job = store.add_file(self.source)
        worker = Worker(store, self.engine)
        self.engine.stopping = worker.stopping
        progressed = threading.Event()
        update = store.update

        def persist(job_id, **fields):
            update(job_id, **fields)
            if fields.get("progress") == 25:
                progressed.set()

        with patch.object(store, "update", side_effect=persist):
            worker.start()
            try:
                self.assertTrue(progressed.wait(timeout=5))
            finally:
                worker.stop()
        self.assertFalse(worker.thread.is_alive())
        self.assertEqual(store.get(job["id"])["status"], "transcribing")
        store.recover()
        self.assertEqual(store.get(job["id"])["status"], "queued")

    def test_windows_console_flag_is_passed_to_native_process(self):
        from types import SimpleNamespace
        from soundnote import whisper_cpp
        native_os = SimpleNamespace(name="nt", environ=__import__("os").environ, read=__import__("os").read)
        popen = subprocess.Popen
        calls = []

        def launch(*args, **kwargs):
            calls.append(kwargs.pop("creationflags"))
            return popen(*args, **kwargs)

        with patch.object(whisper_cpp, "os", native_os), patch.object(
                subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), patch.object(
                subprocess, "Popen", side_effect=launch):
            self.assertEqual(list(self.engine.run([sys.executable, "-c", "print('ready')"])), ["ready"])
        self.assertEqual(calls, [0x08000000])

    def test_windows_crlf_output_is_normalized(self):
        lines = list(self.engine.run([sys.executable, "-c",
                                     "import sys; sys.stdout.buffer.write(b'first\\r\\nsecond\\r\\n')"]))
        self.assertEqual(lines, ["first", "second"])

    def test_nonzero_exit_is_not_silently_completed(self):
        with self.assertLogs(level="ERROR"), self.assertRaises(WhisperError):
            list(self.engine.run([sys.executable, "-c", "import sys; sys.exit(3)"]))

    def test_cancel_silent_native_process_reaps_child(self):
        children = []
        popen = subprocess.Popen

        def launch(*args, **kwargs):
            process = popen(*args, **kwargs)
            children.append(process)
            return process

        with patch("soundnote.whisper_cpp.subprocess.Popen", side_effect=launch):
            stream = self.engine.run([sys.executable, "-c",
                                      "import time; print('ready', flush=True); time.sleep(60)"])
            self.assertEqual(next(stream), "ready")
            self.engine.stopping.set()
            with self.assertRaises(WhisperError):
                list(stream)
        self.assertIsNotNone(children[0].poll())

    def test_closing_stream_reaps_child(self):
        stream = self.engine.run([sys.executable, "-c",
                                  "import time; print('ready', flush=True); time.sleep(60)"])
        self.assertEqual(next(stream), "ready")
        stream.close()


class ModelDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.engine = WhisperEngine(self.temporary.name)

    def response(self, content, expected=None):
        response = io.BytesIO(content)
        response.headers = {"Content-Length": str(len(content) if expected is None else expected)}
        return response

    def test_atomic_download_and_cache_reuse(self):
        with patch("soundnote.whisper_cpp.urllib.request.urlopen", return_value=self.response(b"model")) as download:
            target = self.engine.model_file("small")
            self.assertEqual(target.read_bytes(), b"model")
            self.assertEqual(self.engine.model_file("small"), target)
            download.assert_called_once()
        self.assertEqual(list(self.engine.directory.glob("*.part")), [])

    def test_incomplete_download_leaves_no_model_or_partial(self):
        with patch("soundnote.whisper_cpp.urllib.request.urlopen", return_value=self.response(b"bad", 100)):
            with self.assertRaises(WhisperError):
                self.engine.model_file("small")
        self.assertEqual(list(self.engine.directory.iterdir()), [])

    def test_vad_download_uses_official_repository(self):
        with patch("soundnote.whisper_cpp.urllib.request.urlopen", return_value=self.response(b"vad")) as download:
            self.engine.model_file("silero-v5.1.2", vad=True)
        self.assertEqual(download.call_args.args[0],
                         "https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin")

    def test_stopped_worker_does_not_download(self):
        self.engine.stopping.set()
        with patch("soundnote.whisper_cpp.urllib.request.urlopen") as download, self.assertRaises(WhisperError):
            self.engine.model_file("small")
        download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
