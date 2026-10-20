import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


installer = load_script("install_native")
builder = load_script("build")


class NativeInstallationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.destination = self.root / "whisper"

    def archive(self, files):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        return output.getvalue()

    def install(self, payload, checksum=None):
        checksum = checksum or hashlib.sha256(payload).hexdigest()
        with patch.object(installer, "TARGET", self.root), patch.object(installer, "download", return_value=payload):
            installer.install_archive("https://example.test/tool.zip", self.destination, checksum)

    def test_native_zip_preserves_cli_dlls_and_license(self):
        self.install(self.archive({"bin/whisper-cli.exe": b"cli", "bin/whisper.dll": b"dll", "LICENSE": b"MIT"}))
        self.assertEqual((self.destination / "bin/whisper-cli.exe").read_bytes(), b"cli")
        self.assertEqual((self.destination / "bin/whisper.dll").read_bytes(), b"dll")
        self.assertTrue((self.destination / "LICENSE").is_file())

    def test_corrupt_download_preserves_existing_installation(self):
        self.destination.mkdir()
        (self.destination / "old.exe").write_bytes(b"working")
        with self.assertRaisesRegex(RuntimeError, "checksum"):
            self.install(b"bad download", "0" * 64)
        self.assertEqual((self.destination / "old.exe").read_bytes(), b"working")

    def test_zip_cannot_write_outside_installation(self):
        with self.assertRaisesRegex(RuntimeError, "Unsafe"):
            self.install(self.archive({"../escape.exe": b"bad"}))
        self.assertFalse((self.root / "escape.exe").exists())


class DistributionInputTests(unittest.TestCase):
    def test_windows_build_collects_runtime_dlls_with_engine(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            engine = root / "whisper-cli.exe"
            ffmpeg = root / "ffmpeg.exe"
            library = root / "whisper.dll"
            for path in [engine, ffmpeg, library]:
                path.write_bytes(b"tool")
            binaries, _ = builder.native_files("windows", [str(engine), str(ffmpeg)])
            self.assertIn((str(library), "native"), binaries)

    def test_build_inputs_include_runtime_tools_and_exclude_private_data(self):
        for target in ["macos", "windows"]:
            with self.subTest(target=target):
                command = builder.build_command(target, ["/test/whisper-cli", "/test/ffmpeg"])
                self.assertEqual(command.count("--add-binary"), 2)
                self.assertIn("--windowed", command)
                self.assertFalse(any(str(ROOT / "data") in argument for argument in command))
                self.assertIn(str(ROOT / "scripts/app_entry.py"), command)


if __name__ == "__main__":
    unittest.main()
