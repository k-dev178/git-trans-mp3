import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from soundnote.transcription import AppError, MAX_UPLOAD, Store, Worker, export_text, subtitle_time


class TranscriptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name)/"data")
        self.source = Path(self.temp.name)/"회의.m4a"
        self.source.write_bytes(b"audio-content")

    def test_import_preserves_original_and_existing_database(self):
        job = self.store.add_file(self.source)
        self.assertEqual((job["model"],job["language"],job["status"]),("mid","auto","queued"))
        self.assertEqual(job["options"],{"timestamps":True,"vad_filter":True,"initial_prompt":""})
        copy = Path(self.store.raw(job["id"])["audio_path"])
        self.assertNotEqual(copy,self.source)
        self.assertEqual(copy.read_bytes(),self.source.read_bytes())
        self.assertEqual(Store(self.store.directory).get(job["id"])["filename"],self.source.name)

    def test_model_language_and_options_persist(self):
        job = self.store.add_file(self.source,"high","ko",{"timestamps":False,"vad_filter":False,"initial_prompt":" 고유명사 "})
        self.assertEqual(job["model"],"high")
        self.assertEqual(job["language"],"ko")
        self.assertEqual(job["options"],{"timestamps":False,"vad_filter":False,"initial_prompt":"고유명사"})

    def test_invalid_files_and_settings_create_no_jobs(self):
        invalid = Path(self.temp.name)/"note.txt"
        invalid.write_text("text")
        empty = Path(self.temp.name)/"empty.mp3"
        empty.touch()
        for path in [invalid,empty,Path(self.temp.name)/"missing.mp3",Path(self.temp.name)]:
            with self.subTest(path=path), self.assertRaises(AppError):
                self.store.add_file(path)
        for options in [{"model":"bogus"},{"language":"bogus"},{"options":{"initial_prompt":"x"*1001}}, {"options":{"timestamps":"yes"}}]:
            with self.subTest(options=options), self.assertRaises(AppError):
                self.store.add_file(self.source,**options)
        self.assertEqual(self.store.list(),[])
        self.assertEqual(list(self.store.uploads.iterdir()),[])

    def test_limit_checked_before_copying(self):
        with patch.object(Path,"stat",return_value=SimpleNamespace(st_size=MAX_UPLOAD+1)), patch.object(Path,"is_file",return_value=True):
            with self.assertRaises(AppError):
                Store.validate_file(self.source)

    def test_cancelled_copy_is_cleaned_up(self):
        stop = threading.Event()
        stop.set()
        with self.assertRaisesRegex(AppError,"중단"):
            self.store.add_file(self.source,stop=stop)
        self.assertEqual(list(self.store.uploads.iterdir()),[])
        self.assertEqual(self.store.list(),[])

    def test_progress_uses_segment_time_and_finishes_at_100(self):
        job = self.store.add_file(self.source)
        observed = []

        def segments():
            yield SimpleNamespace(start=0,end=2.5,text=" 첫 문장 ")
            observed.append(self.store.get(job["id"])["progress"])
            yield SimpleNamespace(start=2.5,end=10,text="다음 문장")
            observed.append(self.store.get(job["id"])["progress"])

        engine = SimpleNamespace(transcribe=lambda *args: (segments(),SimpleNamespace(duration=10,language="ko")))
        Worker(self.store,engine).process(job["id"])
        self.assertEqual(observed,[25,99])
        result = self.store.get(job["id"])
        self.assertEqual((result["status"],result["progress"]),("completed",100))
        self.assertEqual(result["text"],"첫 문장\n다음 문장")
        self.assertEqual(len(result["segments"]),2)

    def test_empty_audio_produces_no_invented_text(self):
        job = self.store.add_file(self.source)
        engine = SimpleNamespace(transcribe=lambda *args: (iter([]),SimpleNamespace(duration=5,language="ko")))
        Worker(self.store,engine).process(job["id"])
        self.assertEqual(self.store.get(job["id"])["text"],"")
        self.assertEqual(self.store.get(job["id"])["status"],"completed")

    def test_failure_and_retry_retain_audio(self):
        job = self.store.add_file(self.source)
        engine = SimpleNamespace(transcribe=Mock(side_effect=AppError("모델 설치 필요")))
        with self.assertLogs(level="ERROR"):
            Worker(self.store,engine).process(job["id"])
        self.assertEqual(self.store.get(job["id"])["error"],"모델 설치 필요")
        retried = self.store.retry(job["id"])
        self.assertEqual((retried["status"],retried["progress"],retried["error"]),("queued",0,None))
        self.assertTrue(Path(self.store.raw(job["id"])["audio_path"]).exists())
        with self.assertRaises(AppError):
            self.store.retry(job["id"])

    def test_recovery_restarts_interrupted_work(self):
        interrupted = self.store.add_file(self.source)
        done = self.store.add_file(self.source)
        self.store.update(interrupted["id"],status="transcribing",progress=48,text="途中")
        self.store.update(done["id"],status="completed",progress=100,text="완료")
        (self.store.uploads/"abandoned.part").write_bytes(b"partial")
        self.store.recover()
        recovered = self.store.get(interrupted["id"])
        self.assertEqual((recovered["status"],recovered["progress"],recovered["text"]),("queued",0,""))
        self.assertEqual(self.store.get(done["id"])["text"],"완료")
        self.assertFalse((self.store.uploads/"abandoned.part").exists())

    def test_delete_removes_internal_copy_only(self):
        job = self.store.add_file(self.source)
        with self.assertRaises(AppError):
            self.store.delete(job["id"])
        self.store.update(job["id"],status="completed")
        copy = Path(self.store.raw(job["id"])["audio_path"])
        self.store.delete(job["id"])
        self.assertFalse(copy.exists())
        self.assertTrue(self.source.exists())
        self.assertEqual(self.store.list(),[])

    def test_export_text_and_subtitles(self):
        job = {"text":"안녕하세요","segments":[{"start":1.25,"end":3.5,"text":"안녕하세요"}]}
        self.assertEqual(export_text(job,"txt"),"안녕하세요\n")
        self.assertEqual(export_text(job,"srt"),"1\n00:00:01,250 --> 00:00:03,500\n안녕하세요\n")
        self.assertEqual(subtitle_time(59.9996),"00:01:00,000")



if __name__ == "__main__":
    unittest.main()
