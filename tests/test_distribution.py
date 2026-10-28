import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_script("build")


class DistributionInputTests(unittest.TestCase):
    def test_build_inputs_include_runtime_tools_and_exclude_private_data(self):
        command = builder.build_command(["/test/whisper-cli", "/test/ffmpeg"])
        self.assertEqual(command.count("--add-binary"), 2)
        self.assertIn("--windowed", command)
        self.assertFalse(any(str(ROOT / "data") in argument for argument in command))
        self.assertIn(str(ROOT / "scripts/app_entry.py"), command)
        self.assertIn(str(ROOT / "assets/macos/Soundnote.icns"), command)



if __name__ == "__main__":
    unittest.main()
