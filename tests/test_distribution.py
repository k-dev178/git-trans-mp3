import importlib.util
import os
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_script("build")


class DistributionInputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.native = Path(self.temporary.name)

    def pe(self, name, machine=0x8664):
        path = self.native / name
        data = bytearray(128)
        data[:2] = b"MZ"
        struct.pack_into("<I", data, 0x3c, 64)
        data[64:70] = b"PE\0\0" + struct.pack("<H", machine)
        path.write_bytes(data)
        return path

    def inputs(self):
        for name in ("whisper-cli.exe", "ffmpeg.exe", "ggml.dll"):
            self.pe(name)
        for component in ("whisper.cpp", "ffmpeg"):
            directory = self.native / "licenses" / component
            directory.mkdir(parents=True)
            (directory / "LICENSE").write_text("notice", encoding="utf-8")

    def test_build_inputs_include_runtime_tools_and_exclude_private_data(self):
        command = builder.build_command(["/test/whisper-cli.exe", "/test/ffmpeg.exe"])
        self.assertEqual(command.count("--add-binary"), 2)
        self.assertIn("--windowed", command)
        self.assertFalse(any(str(ROOT / "data") in argument for argument in command))
        self.assertIn(str(ROOT / "scripts/app_entry.py"), command)
        self.assertIn(str(ROOT / "dist/windows"), command)
        self.assertNotIn("--osx-bundle-identifier", command)

    def test_native_inputs_include_dll_and_license_notices(self):
        self.inputs()
        executables, binaries, data = builder.native_files(self.native)
        self.assertEqual(len(executables), 2)
        self.assertEqual(binaries, [(str(self.native / "ggml.dll"), "native")])
        self.assertEqual(len(data), 2)
        self.assertTrue(all(destination.startswith("licenses/native/") for _, destination in data))

    def test_missing_engine_fails_before_build(self):
        with self.assertRaisesRegex(RuntimeError, "Required tool is missing"):
            builder.native_files(self.native)

    def test_missing_license_fails_before_build(self):
        self.inputs()
        (self.native / "licenses/ffmpeg/LICENSE").unlink()
        with self.assertRaisesRegex(RuntimeError, "license files are required"):
            builder.native_files(self.native)

    def test_non_x64_dll_fails_before_build(self):
        self.inputs()
        self.pe("ggml.dll", machine=0x14c)
        with self.assertRaisesRegex(RuntimeError, "Windows x64"):
            builder.native_files(self.native)


if __name__ == "__main__":
    unittest.main()
