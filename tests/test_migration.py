import io
import json
from pathlib import Path
import signal
import unittest
from unittest.mock import Mock, patch

from soundnote.migrate_legacy import stop_legacy


class MigrationTests(unittest.TestCase):
    def test_only_previous_program_in_this_workspace_is_stopped(self):
        project = Path("/private/tmp/soundnote-migration-test")
        reply = io.BytesIO(json.dumps({"app":"soundnote-local","workspace":str(project.resolve()),"pid":12345}).encode())
        opener = Mock()
        opener.open.return_value = reply
        with patch("soundnote.migrate_legacy.urllib.request.build_opener",return_value=opener), patch("soundnote.migrate_legacy.os.kill") as kill:
            self.assertTrue(stop_legacy(project))
            kill.assert_called_once_with(12345,signal.SIGTERM)

    def test_another_workspace_is_not_stopped(self):
        reply = io.BytesIO(json.dumps({"app":"soundnote-local","workspace":"/another/project","pid":12345}).encode())
        opener = Mock()
        opener.open.return_value = reply
        with patch("soundnote.migrate_legacy.urllib.request.build_opener",return_value=opener), patch("soundnote.migrate_legacy.os.kill") as kill:
            self.assertFalse(stop_legacy("/private/tmp/project"))
            kill.assert_not_called()

    def test_unavailable_legacy_service_is_safe(self):
        opener = Mock()
        opener.open.side_effect = OSError("Not available")
        with patch("soundnote.migrate_legacy.urllib.request.build_opener",return_value=opener), patch("soundnote.migrate_legacy.os.kill") as kill:
            self.assertFalse(stop_legacy("/private/tmp/project"))
            kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
