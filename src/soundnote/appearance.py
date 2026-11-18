"""Application appearance, native system following, and saved preferences."""

import json
import logging
from pathlib import Path
import re
import tempfile

from .qt_bootstrap import ensure_qt

if not ensure_qt():
    raise ImportError("PySide6가 필요합니다.")

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

MODES = ("system", "light", "dark")
LIGHT = {
    "window":"#f6f6f7", "surface":"#ffffff", "text":"#242428", "muted":"#6e6e78",
    "border":"#dedee3", "hover":"#f1f1f4", "pressed":"#e8e8ed", "focus":"#c92e3b",
    "disabled_text":"#9999a3", "disabled_bg":"#f0f0f3", "selection":"#fbe8eb", "selected_text":"#8f1f2b",
    "primary":"#c92e3b", "primary_hover":"#ac2330", "primary_disabled":"#d7acb1", "on_primary":"#ffffff",
    "error":"#b83225", "error_bg":"#fff0eb", "notice":"#7b6534", "notice_bg":"#faf5e9", "notice_border":"#e9dfc5",
    "drop":"#f9f9fa", "drop_border":"#c7c7d0", "drop_hover":"#fceff1", "drop_text":"#36363d",
    "radio":"#c92e3b", "radio_border":"#b7b7c2", "radio_ring":"#f7dce0",
    "line":"#ededf1", "header":"#f8f8fa", "track":"#e8e8ee", "success":"#62626c",
    "scroll":"#f6f6f8", "scroll_handle":"#c7c7d0",
}
DARK = {
    "window":"#111113", "surface":"#19191c", "text":"#ececee", "muted":"#a6a6b0",
    "border":"#34343b", "hover":"#25252b", "pressed":"#303037", "focus":"#f06573",
    "disabled_text":"#73737f", "disabled_bg":"#222227", "selection":"#402329", "selected_text":"#ffe4e7",
    "primary":"#d72f40", "primary_hover":"#eb4051", "primary_disabled":"#583039", "on_primary":"#ffffff",
    "error":"#ffab93", "error_bg":"#392622", "notice":"#dfc58e", "notice_bg":"#302b21", "notice_border":"#514735",
    "drop":"#1c1c21", "drop_border":"#484852", "drop_hover":"#302126", "drop_text":"#ececee",
    "radio":"#ed5364", "radio_border":"#767682", "radio_ring":"#4b2830",
    "line":"#2b2b32", "header":"#202025", "track":"#32323b", "success":"#b8b8c1",
    "scroll":"#202025", "scroll_handle":"#50505e",
}

STYLE_TEMPLATE = """
QWidget { font-family: 'Malgun Gothic'; font-size: 13px; color: $text; }
QMainWindow, QDialog, QWidget#content { background: $window; }
QWidget#library { background: $surface; }
QLabel#caption, QLabel#eyebrow { font-size: 10px; color: $muted; }
QLabel#eyebrow { letter-spacing: 2px; }
QLabel#title { font-size: 30px; font-weight: 600; }
QLabel#subtitle { color: $muted; font-size: 13px; }
QLabel#section-title { font-size: 14px; font-weight: 600; }
QLabel#muted { color: $muted; font-size: 12px; }
QLabel#job-status { color: $success; font-size: 12px; }
QLabel#job-status[state="importing"], QLabel#job-status[state="transcribing"] { color: $focus; }
QLabel#job-status[failed="true"] { color: $error; }
QLabel#error { color: $error; background: $error_bg; border-radius: 6px; padding: 11px; }
QLabel#notice { color: $notice; background: $notice_bg; border: 1px solid $notice_border; border-radius: 7px; padding: 12px; }
QLabel#hero-title { font-size: 24px; font-weight: 600; }
QFrame#library-empty { border: 1px dashed $border; border-radius: 10px; }
QFrame#job-card { background: $surface; border: 1px solid $border; border-radius: 12px; }
QFrame#job-error { background: $error_bg; border-radius: 8px; }
QLabel#job-error-title { color: $error; font-weight: 600; }
QLabel#job-error-message { color: $text; }
QLabel#outcome-icon { background: $hover; border-radius: 10px; font-size: 21px; font-weight: 600; }
QLabel#outcome-icon[failed="true"] { background: $error_bg; color: $error; }
QPushButton { background: $surface; border: 1px solid $border; border-radius: 7px; padding: 10px 16px; }
QPushButton:hover { background: $hover; border-color: $focus; }
QPushButton:pressed { background: $pressed; }
QPushButton:focus { border-color: $focus; }
QPushButton:disabled { color: $disabled_text; border-color: $border; background: $disabled_bg; }
QPushButton[compact="true"] { padding: 7px 12px; }
QPushButton#primary { background: $primary; border-color: $primary; color: $on_primary; font-weight: 600; }
QPushButton#primary:hover { background: $primary_hover; }
QPushButton#primary:disabled { background: $primary_disabled; border-color: $primary_disabled; color: $on_primary; }
QPushButton#danger { color: $error; }
QLineEdit, QComboBox, QPlainTextEdit { border: 1px solid $border; border-radius: 6px; padding: 9px; background: $surface; selection-background-color: $selection; selection-color: $selected_text; }
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus { border-color: $focus; }
QComboBox { min-height: 20px; }
QComboBox:disabled { color: $disabled_text; background: $disabled_bg; }
QComboBox::drop-down { border: 0; width: 22px; }
QComboBox QAbstractItemView { background: $surface; color: $text; selection-background-color: $selection; selection-color: $selected_text; }
QFrame#drop-zone { background: $drop; border: 2px dashed $drop_border; border-radius: 10px; }
QFrame#drop-zone[dragging="true"] { background: $drop_hover; border-color: $focus; }
QFrame#drop-zone:hover, QFrame#drop-zone:focus { background: $drop_hover; border-color: $focus; }
QLabel#drop-title { font-size: 17px; font-weight: 600; color: $drop_text; }
QGroupBox { border: 1px solid $border; border-radius: 8px; margin-top: 14px; padding-top: 15px; background: $surface; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; font-weight: 600; }
QRadioButton, QCheckBox { spacing: 9px; }
QRadioButton::indicator { width: 14px; height: 14px; border: 1px solid $radio_border; border-radius: 8px; background: $surface; }
QRadioButton::indicator:checked { background: $radio; border: 3px solid $radio_ring; }
QCheckBox::indicator { width: 15px; height: 15px; }
QTableWidget { background: $surface; border: 0; gridline-color: $line; selection-background-color: $selection; selection-color: $selected_text; }
QTableWidget::item { padding: 11px; border-bottom: 1px solid $line; }
QTableWidget::item:selected { background: $selection; }
QTableWidget#job-list::item { border-bottom: 1px solid $border; }
QTableWidget#job-list::item:hover { background: $hover; }
QTableWidget#job-list::item:selected { background: $selection; color: $selected_text; }
QTableWidget#job-list QHeaderView::section { font-size: 12px; padding: 10px 11px; }
QPlainTextEdit#transcript { font-size: 14px; padding: 14px; border-radius: 8px; }
QLabel#job-status[state="queued"], QLabel#job-status[state="preparing"] { color: $muted; }
QHeaderView::section { background: $header; border: 0; border-bottom: 1px solid $border; padding: 13px; color: $muted; font-size: 11px; }
QProgressBar { background: $track; border: 0; border-radius: 3px; min-height: 5px; max-height: 5px; }
QProgressBar::chunk { background: $primary; border-radius: 3px; }
QScrollArea { border: 0; background: transparent; }
QScrollBar:vertical { background: $scroll; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: $scroll_handle; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QMenu { background: $surface; color: $text; border: 1px solid $border; padding: 5px; }
QMenu::item { padding: 7px 18px; border-radius: 4px; }
QMenu::item:selected { background: $selection; color: $selected_text; }
QMenu::item:disabled { color: $disabled_text; }
QToolTip { background: $surface; color: $text; border: 1px solid $border; padding: 5px 8px; }
"""


def stylesheet(mode):
    colors = DARK if mode == "dark" else LIGHT
    return re.sub(r"\$([a-z_]+)", lambda match: colors[match[1]], STYLE_TEMPLATE)


LIGHT_STYLE = stylesheet("light")


def color_for(name):
    application = QApplication.instance()
    dark = application is not None and application.property("soundnoteTheme") == "dark"
    return (DARK if dark else LIGHT)[name]


class AppearanceSettings:
    def __init__(self, path):
        self.path = Path(path)
        self.data = {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self.data = data
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            logging.warning("Appearance settings could not be read; following system appearance")

    @property
    def mode(self):
        value = self.data.get("appearance", "system")
        return value if value in MODES else "system"

    def save(self, mode):
        if mode not in MODES:
            raise ValueError("Unknown appearance mode")
        data = {**self.data, "appearance": mode}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                    prefix="appearance-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            temporary.replace(self.path)
            self.data = data
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)


class ThemeManager(QObject):
    changed = Signal(str)

    def __init__(self, application, settings_path, parent=None, style_hints=None):
        super().__init__(parent)
        self.application = application
        self.settings = AppearanceSettings(settings_path)
        self.preference = self.settings.mode
        self.resolved_mode = None
        self.hints = style_hints if style_hints is not None else application.styleHints()
        self._native_preference = None
        self.hints.colorSchemeChanged.connect(self._system_changed)
        self.apply()

    def _system_changed(self, scheme):
        # Qt emits this before its native palette update has finished.
        QTimer.singleShot(0, self.apply)

    def set_mode(self, mode):
        if mode not in MODES:
            raise ValueError("Unknown appearance mode")
        if mode == self.preference:
            return
        # A failed save must not change the current selection or appearance.
        self.settings.save(mode)
        self.preference = mode
        self.apply()

    def apply(self):
        if self._native_preference != self.preference:
            self._native_preference = self.preference
            self.hints.setColorScheme({"system":Qt.ColorScheme.Unknown,
                "light":Qt.ColorScheme.Light, "dark":Qt.ColorScheme.Dark}[self.preference])
        mode = self.preference
        if mode == "system":
            mode = "dark" if self.hints.colorScheme() == Qt.ColorScheme.Dark else "light"
        self.resolved_mode = mode
        colors = DARK if mode == "dark" else LIGHT
        palette = QPalette(self.application.style().standardPalette())
        roles = {"Window":"window", "WindowText":"text", "Base":"surface", "AlternateBase":"hover",
                 "Text":"text", "Button":"surface", "ButtonText":"text", "ToolTipBase":"surface",
                 "ToolTipText":"text", "Highlight":"selection", "HighlightedText":"selected_text",
                 "PlaceholderText":"muted", "Link":"focus", "LinkVisited":"focus"}
        for role, key in roles.items():
            palette.setColor(getattr(QPalette.ColorRole, role), QColor(colors[key]))
        for role in [QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText]:
            palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(colors["disabled_text"]))
        self.application.setProperty("soundnoteTheme", mode)
        self.application.setPalette(palette)
        self.application.setStyleSheet(stylesheet(mode))
        for widget in self.application.allWidgets():
            widget.update()
        self.changed.emit(mode)
