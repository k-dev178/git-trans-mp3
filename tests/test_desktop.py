import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from soundnote.qt_bootstrap import ensure_qt

QT_AVAILABLE = ensure_qt()
if QT_AVAILABLE:
    from PySide6.QtCore import QCoreApplication, QEvent, QMimeData, QPoint, QPointF, Qt, QUrl
    from PySide6.QtGui import QContextMenuEvent, QDragEnterEvent, QDropEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMessageBox
    from soundnote.desktop import MainWindow, STYLE
    from soundnote.transcription import Store, Worker


@unittest.skipUnless(QT_AVAILABLE,"PySide6 is required for real GUI tests")
class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])
        cls.application.setStyle("Fusion")
        cls.application.setStyleSheet(STYLE)
        cls.application.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name)/"data")
        self.worker = Worker(self.store)
        self.window = MainWindow(self.store,self.worker,tray_enabled=False)
        self.window.show()
        self.application.processEvents()
        self.source = Path(self.temp.name)/"회의.m4a"
        self.source.write_bytes(b"audio-data")

    def tearDown(self):
        self.window.timer.stop()
        self.window.quitting = True
        self.worker.stopping.set()
        self.worker.wakeup.set()
        if hasattr(self,"release"):
            self.release.set()
        if self.worker.thread.is_alive():
            self.worker.thread.join(2)
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.application.processEvents()
        self.temp.cleanup()

    def wait_for(self, condition, timeout=2):
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            self.application.processEvents()
            if condition():
                return
            QTest.qWait(10)
        self.fail("GUI condition did not become true")

    def test_first_screen_is_library_and_plus_opens_settings(self):
        self.assertIs(self.window.stack.currentWidget(),self.window.library)
        self.window.library.new_button.click()
        self.assertIs(self.window.stack.currentWidget(),self.window.add_page)
        self.assertEqual(self.window.add_page.drop.title.text(),"전사할 파일을 끌어다 놓아주세요")
        self.assertFalse(self.window.add_page.confirm.isEnabled())
        self.assertTrue(self.window.add_page.drop.isVisible())
        self.assertFalse(self.window.add_page.back.isVisible())
        self.assertFalse(self.window.add_page.options.isVisible())
        self.assertFalse(self.window.add_page.footer.isVisible())
        self.assertFalse(self.window.add_page.confirm.isVisible())
        self.assertEqual(self.window.add_page.language.currentData(),"auto")
        self.assertTrue(self.window.add_page.radios["mid"].isChecked())

    def test_stop_marker_quits_application_and_preserves_store(self):
        marker = self.store.directory / "stop-app"
        marker.write_text("stop")
        with patch.object(self.window, "quit_application") as quit_application:
            self.window.refresh()
        quit_application.assert_called_once()
        self.assertTrue(self.store.directory.is_dir())

    def test_settings_selects_saves_and_applies_appearance_without_leaving_list(self):
        import json
        from PySide6.QtGui import QPalette
        self.window.settings_action.trigger()
        dialog = self.window.settings_dialog
        self.assertTrue(dialog.isVisible())
        self.assertEqual(dialog.appearance.currentData(), "system")
        self.assertIs(self.window.stack.currentWidget(), self.window.library)
        dialog.appearance.setCurrentIndex(dialog.appearance.findData("dark"))
        self.application.processEvents()
        self.assertEqual(self.window.theme.resolved_mode, "dark")
        self.assertLess(self.window.library.table.palette().color(QPalette.ColorRole.Base).lightness(), 80)
        saved = json.loads((self.store.directory / "settings.json").read_text())
        self.assertEqual(saved["appearance"], "dark")
        self.window.show_add()
        self.assertEqual(self.window.add_page.prompt.palette().color(QPalette.ColorRole.Base).lightness() < 80, True)
        dialog.appearance.setCurrentIndex(dialog.appearance.findData("light"))
        self.application.processEvents()
        self.assertGreater(self.window.add_page.prompt.palette().color(QPalette.ColorRole.Base).lightness(), 200)
        dialog.appearance.setCurrentIndex(dialog.appearance.findData("system"))
        self.assertEqual(self.window.theme.preference, "system")
        self.assertEqual(json.loads((self.store.directory / "settings.json").read_text())["appearance"], "system")

    def test_native_file_drop_activates_confirm(self):
        self.window.show_add()
        drop = self.window.add_page.drop
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(self.source))])
        enter = QDragEnterEvent(QPoint(20,20),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(drop,enter)
        event = QDropEvent(QPointF(20,20),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(drop,event)
        self.assertTrue(self.window.add_page.confirm.isEnabled())
        self.assertTrue(self.window.add_page.options.isVisible())
        self.assertTrue(self.window.add_page.confirm.isVisible())
        self.assertEqual(Path(self.window.add_page.path), self.source)
        self.assertEqual(self.store.list(), [])
        self.window.show_home()
        self.window.library.new_button.click()
        self.assertIsNone(self.window.add_page.path)
        self.assertFalse(self.window.add_page.options.isVisible())
        self.assertFalse(self.window.add_page.confirm.isVisible())

    def test_click_opens_native_file_picker(self):
        self.window.show_add()
        with patch("soundnote.desktop.QFileDialog.getOpenFileName",return_value=(str(self.source),"")):
            self.window.add_page.drop.pick_file()
        self.assertTrue(self.window.add_page.confirm.isEnabled())

    def test_invalid_file_does_not_activate_confirm(self):
        invalid = Path(self.temp.name)/"note.txt"
        invalid.write_text("hello")
        self.window.show_add()
        self.window.add_page.select_file(str(invalid))
        self.assertFalse(self.window.add_page.confirm.isEnabled())
        self.assertFalse(self.window.add_page.error.isHidden())
        self.assertFalse(self.window.add_page.options.isVisible())
        self.assertFalse(self.window.add_page.confirm.isVisible())

    def test_keyboard_opens_drop_area_file_picker(self):
        self.window.show_add()
        drop = self.window.add_page.drop
        drop.setFocus()
        with patch("soundnote.desktop.QFileDialog.getOpenFileName", return_value=(str(self.source), "")):
            QTest.keyClick(drop, Qt.Key.Key_Return)
        self.assertEqual(self.window.add_page.path, str(self.source))
        self.assertTrue(self.window.add_page.confirm.isEnabled())

    def test_language_defaults_to_auto_and_allows_manual_selection(self):
        self.window.show_add()
        self.window.add_page.select_file(str(self.source))
        language = self.window.add_page.language
        self.assertTrue(language.isVisible())
        self.assertEqual(language.currentData(), "auto")
        language.setCurrentIndex(language.findData("ja"))
        with patch.object(self.window, "start_job") as start:
            self.window.add_page.start_requested.disconnect()
            self.window.add_page.start_requested.connect(start)
            self.window.add_page.submit()
            self.assertEqual(start.call_args.args[2], "ja")
        self.window.add_page.reset()
        self.assertEqual(language.currentData(), "auto")

    def test_confirm_starts_background_progress_and_close_keeps_worker_alive(self):
        self.release = threading.Event()

        def stream():
            yield SimpleNamespace(start=0,end=2.5,text="첫 번째 문장")
            self.release.wait(3)
            yield SimpleNamespace(start=2.5,end=10,text="두 번째 문장")

        self.worker.engine = SimpleNamespace(transcribe=lambda *args: (stream(),SimpleNamespace(duration=10,language="ko")))
        self.worker.start()
        self.window.show_add()
        self.window.add_page.select_file(str(self.source))
        self.window.add_page.radios["high"].setChecked(True)
        self.window.add_page.language.setCurrentIndex(1)
        self.window.add_page.confirm.click()
        self.assertIs(self.window.stack.currentWidget(),self.window.started_page)
        self.wait_for(lambda: bool(self.store.list()) and self.store.list()[0]["progress"]==25)
        self.window.show_home()
        self.window.refresh()
        self.assertEqual(self.window.library.table.rowCount(),1)
        status = self.window.library.table.cellWidget(0,1)
        self.assertEqual(status.text.text(),"전사 중 · 25%")
        self.assertFalse(status.spinner.isHidden())
        job = self.store.list()[0]
        self.assertEqual((job["model"],job["language"]),("high","ko"))
        self.window.close()
        self.assertFalse(self.window.isVisible())
        self.assertFalse(self.worker.stopping.is_set())
        self.assertTrue(self.worker.thread.is_alive())
        self.release.set()
        self.wait_for(lambda: self.store.list()[0]["status"]=="completed")
        self.window.restore()
        self.window.show_detail(job["id"])
        self.assertIn("첫 번째 문장",self.window.detail.text.toPlainText())
        self.assertIn("두 번째 문장",self.window.detail.text.toPlainText())

    def completed_job(self, filename="회의.m4a"):
        source = Path(self.temp.name)/filename
        source.write_bytes(b"audio")
        job = self.store.add_file(source)
        self.store.update(job["id"],status="completed",progress=100,text="기록 내용",segments='[{"start":0,"end":3,"text":"기록 내용"}]',detected_language="ko",duration=3)
        return self.store.get(job["id"])

    def test_list_shows_all_records_and_returns_from_detail(self):
        self.assertTrue(self.window.library.empty_state.isVisible())
        done = self.completed_job()
        queued = self.store.add_file(self.source)
        self.window.refresh()
        table = self.window.library.table
        self.assertEqual(table.rowCount(),2)
        self.assertTrue(self.window.library.empty_state.isHidden())
        ids = {table.item(row,0).data(Qt.ItemDataRole.UserRole) for row in range(table.rowCount())}
        self.assertEqual(ids,{done["id"],queued["id"]})
        done_row = next(row for row in range(table.rowCount())
                        if table.item(row, 0).data(Qt.ItemDataRole.UserRole) == done["id"])
        self.assertEqual(table.item(done_row, 2).text(), "00:03")
        point = table.visualItemRect(table.item(done_row, 3)).center()
        QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.assertIs(self.window.stack.currentWidget(), self.window.detail)
        self.assertEqual(self.window.detail.job["id"], done["id"])
        self.window.detail.home_requested.emit()
        self.assertIs(self.window.stack.currentWidget(),self.window.library)
        self.assertEqual(table.rowCount(),2)

    def open_list_menu(self, row, column=0):
        self.window.refresh()
        table = self.window.library.table
        point = table.visualItemRect(table.item(row, column)).center()
        QTest.mouseClick(table.viewport(), Qt.MouseButton.RightButton, pos=point)
        event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, point,
                                  table.viewport().mapToGlobal(point))
        QApplication.sendEvent(table.viewport(), event)
        self.application.processEvents()
        self.assertIs(self.window.stack.currentWidget(), self.window.library)
        self.assertTrue(self.window.library.context_menu.isVisible())

    def test_list_context_delete_targets_clicked_row_and_preserves_original(self):
        target = self.completed_job("삭제할 음성.m4a")
        other = self.completed_job("유지할 음성.m4a")
        self.window.refresh()
        table = self.window.library.table
        row = next(row for row in range(table.rowCount())
                   if table.item(row, 0).data(Qt.ItemDataRole.UserRole) == target["id"])
        table.selectRow(1 - row)
        self.open_list_menu(row, column=1)
        self.assertTrue(self.window.library.delete_action.isEnabled())
        self.window.library.context_menu.hide()
        with patch("soundnote.desktop.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            self.window.library.delete_action.trigger()
        self.assertEqual([job["id"] for job in self.store.list()], [other["id"]])
        self.assertTrue((Path(self.temp.name) / "삭제할 음성.m4a").exists())
        self.assertEqual(table.rowCount(), 1)

    def test_list_context_delete_can_be_cancelled(self):
        job = self.completed_job()
        self.open_list_menu(0)
        self.window.library.context_menu.hide()
        with patch("soundnote.desktop.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
            self.window.library.delete_action.trigger()
        self.assertEqual(self.store.get(job["id"])["status"], "completed")

    def test_list_context_delete_disabled_for_active_jobs(self):
        job = self.store.add_file(self.source)
        for status in ("queued", "preparing", "transcribing"):
            with self.subTest(status=status):
                self.store.update(job["id"], status=status)
                self.open_list_menu(0)
                self.assertFalse(self.window.library.delete_action.isEnabled())
                self.window.library.context_menu.hide()

    def test_list_context_menu_ignores_empty_space(self):
        self.window.library.show_context_menu(QPoint(10, 200))
        self.assertFalse(self.window.library.context_menu.isVisible())

    def test_detail_copy_and_subtitle_export(self):
        job = self.completed_job()
        self.window.show_detail(job["id"])
        self.window.detail.copy_button.click()
        self.assertEqual(QApplication.clipboard().text(),"기록 내용")
        self.assertEqual(self.window.detail.copy_button.text(), "복사됨")
        destination = Path(self.temp.name)/"result.srt"
        with patch("soundnote.desktop.QFileDialog.getSaveFileName",return_value=(str(destination),"")):
            self.window.detail.srt_button.click()
        self.assertIn("00:00:00,000 --> 00:00:03,000", destination.read_text(encoding="utf-8"))
        other = self.completed_job("다른 기록.m4a")
        self.window.show_detail(other["id"])
        self.assertEqual(self.window.detail.copy_button.text(), "복사")

    def test_failed_job_retry_and_delete(self):
        job = self.store.add_file(self.source)
        self.store.update(job["id"],status="failed",error="전사 실패")
        self.window.started_id = job["id"]
        started = self.window.started_page
        self.window.stack.setCurrentWidget(started)
        self.window.refresh()
        self.assertTrue(started.error.isVisible())
        self.assertTrue(started.background_help.isHidden())
        started.new_button.click()
        self.assertIs(self.window.stack.currentWidget(), self.window.add_page)
        self.window.stack.setCurrentWidget(started)
        started.detail_button.click()
        self.assertIs(self.window.stack.currentWidget(), self.window.detail)
        self.assertEqual(self.window.detail.error.message.text(), "전사 실패")
        self.assertTrue(self.window.detail.transcript.isHidden())
        self.assertFalse(self.window.detail.retry_button.isHidden())
        self.window.detail.retry_button.click()
        self.assertEqual(self.store.get(job["id"])["status"],"queued")
        self.assertTrue(self.window.detail.error.isHidden())
        self.assertFalse(self.window.detail.transcript.isHidden())
        self.store.update(job["id"],status="failed")
        self.window.refresh()
        with patch("soundnote.desktop.QMessageBox.question",return_value=QMessageBox.StandardButton.Yes):
            self.window.detail.delete_button.click()
        self.assertEqual(self.store.list(),[])
        self.assertTrue(self.source.exists())


if __name__ == "__main__":
    unittest.main()
