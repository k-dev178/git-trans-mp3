import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from soundnote import launcher, paths
from soundnote.instance import InstanceLock
from soundnote.whisper_cpp import WhisperEngine


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def runtime(self):
        (self.directory / "desktop-runtime.json").write_text(json.dumps({
            "app": "soundnote-desktop", "pid": 12345, "workspace": str(paths.ROOT)}), encoding="utf-8")

    def test_lock_excludes_other_process_and_releases_after_exit(self):
        source = str(paths.ROOT / "src")
        command = [sys.executable, "-c", f"""
import sys
sys.path.insert(0, {source!r})
from soundnote.instance import InstanceLock
with InstanceLock(sys.argv[1]) as lock:
    print(lock.acquire(), flush=True)
    sys.stdin.readline()
""", str(self.directory)]
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), "True")
            self.assertTrue(launcher.data_locked(self.directory))
        finally:
            process.communicate("\n", timeout=5)
        self.assertFalse(launcher.data_locked(self.directory))

    def test_stale_runtime_does_not_block_launch(self):
        self.runtime()
        self.assertIsNone(launcher.running_desktop(self.directory))

    def test_second_launch_reopens_and_stop_uses_marker_without_pid_signals(self):
        self.runtime()
        with InstanceLock(self.directory) as lock:
            self.assertTrue(lock.acquire())
            for arguments, marker in [([], "show-window"), (["--stop"], "stop-app")]:
                with self.subTest(arguments=arguments), patch.object(
                        sys, "argv", ["soundnote", "--data-dir", str(self.directory), *arguments]), patch(
                        "soundnote.launcher.subprocess.Popen") as popen, patch("os.kill") as kill:
                    launcher.main()
                    self.assertTrue((self.directory / marker).is_file())
                    popen.assert_not_called()
                    kill.assert_not_called()

    def test_source_data_stays_in_original_directory(self):
        with patch.object(paths, "FROZEN", False), patch.dict(os.environ, {}, clear=True):
            self.assertEqual(paths.data_directory(), paths.ROOT / "data")

    def test_frozen_data_is_separate_from_application_files(self):
        with patch.object(paths, "FROZEN", True), patch.dict(os.environ, {}, clear=True):
            self.assertEqual(paths.data_directory(), Path.home() / "Library/Application Support/Soundnote")

    def test_data_directory_override(self):
        with patch.dict(os.environ, {"SOUNDNOTE_DATA_DIR": str(self.directory)}):
            self.assertEqual(paths.data_directory(), self.directory.resolve())

    def test_packaged_engine_is_found_without_path(self):
        binary = self.directory / "whisper-cli"
        binary.write_bytes(b"engine")
        with patch("soundnote.whisper_cpp.native_directory", return_value=self.directory), patch.dict(os.environ, {"PATH": ""}):
            self.assertEqual(WhisperEngine.executable("whisper-cli"), str(binary))


if __name__ == "__main__":
    unittest.main()
