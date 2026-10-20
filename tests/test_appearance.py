import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from soundnote.qt_bootstrap import ensure_qt

QT_AVAILABLE = ensure_qt()
if QT_AVAILABLE:
    from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt, Signal
    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import QApplication
    from soundnote.appearance import AppearanceSettings, ThemeManager

    class FakeSystemAppearance(QObject):
        colorSchemeChanged = Signal(Qt.ColorScheme)

        def __init__(self, system):
            super().__init__()
            self.system = system
            self.override = Qt.ColorScheme.Unknown

        def colorScheme(self):
            return self.system if self.override == Qt.ColorScheme.Unknown else self.override

        def setColorScheme(self, override):
            before = self.colorScheme()
            self.override = override
            if before != self.colorScheme():
                self.colorSchemeChanged.emit(self.colorScheme())

        def change_system(self, scheme):
            before = self.colorScheme()
            self.system = scheme
            if before != self.colorScheme():
                self.colorSchemeChanged.emit(self.colorScheme())


@unittest.skipUnless(QT_AVAILABLE, "PySide6 is required")
class AppearanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])
        cls.application.setStyle("Fusion")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/"settings.json"
        self.hints = FakeSystemAppearance(Qt.ColorScheme.Dark)
        self.managers = []

    def manager(self):
        result = ThemeManager(self.application, self.path, style_hints=self.hints)
        self.managers.append(result)
        return result

    def tearDown(self):
        self.application.processEvents()
        for manager in self.managers:
            manager.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.temp.cleanup()

    def test_first_run_always_follows_system_including_dark_systems(self):
        manager = self.manager()
        self.assertEqual(manager.preference, "system")
        self.assertEqual(manager.resolved_mode, "dark")
        self.assertEqual(self.hints.override, Qt.ColorScheme.Unknown)
        self.assertFalse(self.path.exists())
        self.assertLess(self.application.palette().color(QPalette.ColorRole.Window).lightness(), 80)

    def test_system_switches_in_both_directions_while_running(self):
        manager = self.manager()
        self.hints.change_system(Qt.ColorScheme.Light)
        self.application.processEvents()
        self.assertEqual(manager.resolved_mode, "light")
        self.assertGreater(self.application.palette().color(QPalette.ColorRole.Base).lightness(), 200)
        self.hints.change_system(Qt.ColorScheme.Dark)
        self.application.processEvents()
        self.assertEqual(manager.resolved_mode, "dark")
        self.assertFalse(self.path.exists())

    def test_manual_modes_remain_fixed_and_system_restores_current_os_mode(self):
        manager = self.manager()
        manager.set_mode("light")
        self.hints.change_system(Qt.ColorScheme.Light)
        self.hints.change_system(Qt.ColorScheme.Dark)
        self.application.processEvents()
        self.assertEqual(manager.resolved_mode, "light")
        manager.set_mode("system")
        self.application.processEvents()
        self.assertEqual(manager.resolved_mode, "dark")
        manager.set_mode("dark")
        self.hints.change_system(Qt.ColorScheme.Light)
        self.application.processEvents()
        self.assertEqual(manager.resolved_mode, "dark")
        manager.set_mode("system")
        self.application.processEvents()
        self.assertEqual(manager.resolved_mode, "light")

    def test_selection_survives_reload_and_preserves_other_settings(self):
        self.path.write_text(json.dumps({"another_setting":42}))
        manager = self.manager()
        manager.set_mode("dark")
        self.assertEqual(json.loads(self.path.read_text()), {"another_setting":42, "appearance":"dark"})
        self.hints.change_system(Qt.ColorScheme.Light)
        reloaded = self.manager()
        self.assertEqual(reloaded.preference, "dark")
        self.assertEqual(reloaded.resolved_mode, "dark")

    def test_saved_system_mode_is_not_resolved_into_a_fixed_mode(self):
        manager = self.manager()
        manager.set_mode("light")
        manager.set_mode("system")
        self.assertEqual(json.loads(self.path.read_text())["appearance"], "system")
        self.hints.change_system(Qt.ColorScheme.Light)
        reloaded = self.manager()
        self.assertEqual(reloaded.preference, "system")
        self.assertEqual(reloaded.resolved_mode, "light")

    def test_bad_settings_fall_back_to_system(self):
        for content in ["broken json", "[]", '{"appearance":"unknown"}']:
            with self.subTest(content=content):
                self.path.write_text(content)
                self.assertEqual(AppearanceSettings(self.path).mode, "system")

    def test_failed_save_keeps_current_mode_and_does_not_create_partial_settings(self):
        manager = self.manager()
        with patch.object(manager.settings, "save", side_effect=OSError("Read only")):
            with self.assertRaises(OSError):
                manager.set_mode("light")
        self.assertEqual(manager.preference, "system")
        self.assertEqual(manager.resolved_mode, "dark")
        self.assertFalse(self.path.exists())
