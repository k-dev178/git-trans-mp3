"""Soundnote desktop application: Qt widgets, file drops, and a local worker."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import signal
import sys
import threading

from .qt_bootstrap import ensure_qt
from .instance import InstanceLock
from .paths import data_directory

if not ensure_qt():
    raise ImportError("GUI 실행에 PySide6가 필요합니다. 운영체제에 맞는 설치 파일을 실행해 주세요.")

from PySide6.QtCore import QEvent, QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QMainWindow,
    QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QRadioButton,
    QScrollArea, QStackedWidget, QSystemTrayIcon, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from .transcription import ACTIVE, ROOT, AppError, Store, WhisperEngine, Worker, export_text

LANGUAGE_LABELS = {"auto":"자동 감지", "ko":"한국어", "en":"영어", "ja":"일본어", "zh":"중국어",
    "es":"스페인어", "fr":"프랑스어", "de":"독일어", "it":"이탈리아어", "pt":"포르투갈어",
    "ru":"러시아어", "vi":"베트남어", "th":"태국어", "ar":"아랍어"}
MODEL_LABELS = {"low":"Low", "mid":"Mid", "high":"High"}

from .appearance import LIGHT_STYLE as STYLE, ThemeManager, color_for



def label(text="", name=None, wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(wrap)
    if name:
        widget.setObjectName(name)
    return widget


def button(text, handler=None, primary=False):
    widget = QPushButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary:
        widget.setObjectName("primary")
    if handler:
        widget.clicked.connect(handler)
    return widget


def bytes_label(size):
    if size < 1024:
        return f"{size} B"
    if size < 1024**2:
        return f"{size / 1024:.1f} KB"
    if size < 1024**3:
        return f"{size / 1024**2:.1f} MB"
    return f"{size / 1024**3:.2f} GB"


def clock_label(seconds):
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"


def status_label(job):
    status = job["status"]
    if status == "importing":
        return f"파일 준비 중 · {job['progress']:g}%"
    if status == "queued":
        return "전사 대기 중"
    if status == "preparing":
        return "모델 준비 중"
    if status == "transcribing":
        return f"전사 중 · {job['progress']:g}%"
    return "전사 완료" if status == "completed" else "전사 실패"


class WaveMark(QWidget):
    def __init__(self, size=44, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color_for("primary")))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 11, 11)
        painter.setPen(QPen(QColor(color_for("on_primary")), max(2, self.width()/22), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for x, height in [(0.25, .2), (.375, .45), (.5, .65), (.625, .45), (.75, .2)]:
            painter.drawLine(int(x*self.width()), int((.5-height/2)*self.height()),
                             int(x*self.width()), int((.5+height/2)*self.height()))


def app_icon():
    mark = WaveMark(128)
    image = QPixmap(128, 128)
    image.fill(Qt.GlobalColor.transparent)
    mark.render(image)
    return QIcon(image)


class Spinner(QWidget):
    def __init__(self, size=17, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.tick)

    def tick(self):
        self.angle = (self.angle + 12) % 360
        self.update()

    def showEvent(self, event):
        self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(2, 2, -2, -2)
        painter.setPen(QPen(QColor(color_for("track")), 2))
        painter.drawEllipse(rect)
        painter.setPen(QPen(QColor(color_for("primary")), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect, -self.angle*16, 100*16)


class JobStatus(QWidget):
    def __init__(self, job, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 14, 8)
        layout.setSpacing(7)
        line = QHBoxLayout()
        self.spinner = Spinner()
        self.text = label("", "job-status")
        line.addWidget(self.spinner)
        line.addWidget(self.text)
        line.addStretch()
        layout.addLayout(line)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.update_job(job)

    def update_job(self, job):
        active = job["status"] in ACTIVE or job["status"] == "importing"
        self.spinner.setVisible(active)
        self.progress.setVisible(active)
        self.text.setText(status_label(job))
        self.progress.setValue(round(job["progress"]))
        failed = job["status"] == "failed"
        if self.text.property("state") != job["status"]:
            self.text.setProperty("state", job["status"])
            self.text.setProperty("failed", failed)
            self.text.style().unpolish(self.text)
            self.text.style().polish(self.text)


class DropArea(QFrame):
    file_selected = Signal(str)
    invalid_drop = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("drop-zone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("전사할 파일을 끌어다 놓거나 클릭해서 선택")
        self.setMinimumHeight(176)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 24, 20, 24)
        layout.setSpacing(12)
        wave = WaveMark(40)
        layout.addWidget(wave, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.title = label("전사할 파일을 끌어다 놓아주세요", "drop-title", True)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title)
        self.caption = label("또는 클릭해서 파일 선택  ·  MP3, M4A, WAV 등  ·  최대 2GB", "muted", True)
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.caption)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.pick_file()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.pick_file()
            event.accept()
            return
        super().keyPressEvent(event)

    def pick_file(self):
        filename, _ = QFileDialog.getOpenFileName(self, "전사할 음성 파일 선택", "",
            "음성 파일 (*.mp3 *.m4a *.wav *.flac *.ogg *.aac *.opus *.aiff *.aif *.mp4 *.webm)")
        if filename:
            self.file_selected.emit(filename)

    def set_dragging(self, value):
        self.setProperty("dragging", value)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and self.isEnabled():
            event.acceptProposedAction()
            self.set_dragging(True)

    def dragLeaveEvent(self, event):
        self.set_dragging(False)

    def dropEvent(self, event):
        self.set_dragging(False)
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if len(paths) != 1:
            self.invalid_drop.emit("한 번에 하나의 음성 파일을 추가해 주세요.")
            return
        event.acceptProposedAction()
        self.file_selected.emit(paths[0])


class AddPage(QWidget):
    start_requested = Signal(str, str, str, dict)
    home_requested = Signal()

    def __init__(self):
        super().__init__()
        self.path = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 16, 24, 20)
        outer.setSpacing(12)
        self.back = button("←  전사 목록으로", self.home_requested.emit)
        self.back.setProperty("compact", True)
        self.back.setFixedWidth(155)
        outer.addWidget(self.back, alignment=Qt.AlignmentFlag.AlignLeft)
        cancel = QAction(self)
        cancel.setShortcut(QKeySequence(Qt.Key.Key_Escape))
        cancel.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        cancel.triggered.connect(self.home_requested.emit)
        self.addAction(cancel)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("content")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 10, 8)
        layout.setSpacing(16)
        self.drop = DropArea()
        self.drop.file_selected.connect(self.select_file)
        self.drop.invalid_drop.connect(self.show_error)
        layout.addWidget(self.drop)
        self.error = label("", "error", True)
        self.error.hide()
        layout.addWidget(self.error)
        self.options = QWidget()
        options_layout = QVBoxLayout(self.options)
        options_layout.setContentsMargins(0, 0, 0, 0)
        options_layout.setSpacing(16)
        engine_notice = label("전사 엔진 설치가 필요합니다. 운영체제에 맞는 설치 파일을 실행한 뒤 앱을 다시 실행해 주세요.", "notice", True)
        engine_notice.setVisible(not WhisperEngine.available())
        options_layout.addWidget(engine_notice)
        models = QGroupBox("전사 모델")
        choices = QHBoxLayout(models)
        choices.setContentsMargins(18, 19, 18, 17)
        self.models = QButtonGroup(self)
        self.radios = {}
        for index, (key, text, description) in enumerate([
            ("low", "Low", "가볍고 빠르게\n짧은 메모 · 간단한 녹음"),
            ("mid", "Mid · 추천", "속도와 정확도의 균형\n회의 · 인터뷰 · 일상 기록"),
            ("high", "High", "더 꼼꼼하고 정확하게\n긴 강의 · 복잡한 대화")]):
            card = QVBoxLayout()
            radio = QRadioButton(text)
            self.models.addButton(radio, index)
            self.radios[key] = radio
            card.addWidget(radio)
            card.addSpacing(7)
            card.addWidget(label(description, "muted", True))
            choices.addLayout(card, 1)
        self.radios["mid"].setChecked(True)
        options_layout.addWidget(models)
        language_row = QHBoxLayout()
        language_row.addWidget(label("음성 언어", "muted"), 1)
        self.language = QComboBox()
        self.language.setAccessibleName("음성 언어")
        self.language.setToolTip("자동 감지를 선택하면 영어·일본어 등 음성의 언어를 자동으로 인식합니다.")
        for key, text in LANGUAGE_LABELS.items():
            self.language.addItem(text, key)
        self.language.setMinimumWidth(200)
        language_row.addWidget(self.language)
        options_layout.addLayout(language_row)
        advanced = QGroupBox("세부 설정")
        advanced.setCheckable(True)
        advanced.setChecked(False)
        advanced_layout = QVBoxLayout(advanced)
        self.advanced_body = QWidget()
        controls = QVBoxLayout(self.advanced_body)
        controls.setContentsMargins(8, 3, 8, 8)
        controls.setSpacing(13)
        self.timestamps = QCheckBox("타임스탬프 표시")
        self.timestamps.setChecked(True)
        self.vad = QCheckBox("무음 구간 건너뛰기")
        self.vad.setChecked(True)
        controls.addWidget(self.timestamps)
        controls.addWidget(self.vad)
        controls.addWidget(label("참고 단어 · 선택", "muted"))
        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText("이름이나 전문 용어 등 참고할 단어를 입력해 주세요. (최대 1,000자)")
        self.prompt.setMaximumHeight(82)
        controls.addWidget(self.prompt)
        advanced_layout.addWidget(self.advanced_body)
        self.advanced_body.hide()
        advanced.toggled.connect(self.advanced_body.setVisible)
        self.advanced = advanced
        options_layout.addWidget(advanced)
        options_layout.addWidget(label("처음 사용하는 모델은 다운로드 시간이 필요할 수 있어요.", "muted"))
        layout.addWidget(self.options)
        layout.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        self.footer = QWidget()
        footer = QHBoxLayout(self.footer)
        footer.setContentsMargins(0, 0, 0, 0)
        footer.addWidget(label("음성과 결과는 이 컴퓨터에 저장됩니다.", "muted"), 1)
        self.confirm = button("확인 · 전사 시작  →", self.submit, primary=True)
        self.confirm.setEnabled(False)
        footer.addWidget(self.confirm)
        outer.addWidget(self.footer)
        self.reset()

    def reset(self):
        self.path = None
        self.drop.setMinimumHeight(176)
        self.drop.layout().setContentsMargins(20, 24, 20, 24)
        self.drop.title.setText("전사할 파일을 끌어다 놓아주세요")
        self.drop.title.setToolTip("")
        self.drop.caption.setText("또는 클릭해서 파일 선택  ·  MP3, M4A, WAV 등  ·  최대 2GB")
        self.radios["mid"].setChecked(True)
        self.language.setCurrentIndex(0)
        self.timestamps.setChecked(True)
        self.vad.setChecked(True)
        self.prompt.clear()
        self.advanced.setChecked(False)
        self.error.hide()
        self.confirm.setEnabled(False)
        self.back.hide()
        self.options.hide()
        self.footer.hide()

    def show_error(self, message):
        self.error.setText(message)
        self.error.show()

    def select_file(self, filename):
        try:
            size = Store.validate_file(filename)
        except (AppError, OSError) as exc:
            self.show_error(str(exc))
            return
        self.path = filename
        self.error.hide()
        self.drop.setMinimumHeight(144)
        self.drop.layout().setContentsMargins(20, 12, 20, 12)
        self.drop.title.setText(Path(filename).name)
        self.drop.title.setToolTip(str(filename))
        self.drop.caption.setText(f"{bytes_label(size)}  ·  클릭해서 다른 파일 선택")
        self.back.show()
        self.options.show()
        self.footer.show()
        self.confirm.setEnabled(True)

    def submit(self):
        if not self.path:
            return
        if len(self.prompt.toPlainText()) > 1000:
            self.show_error("참고 단어는 1,000자 이내로 입력해 주세요.")
            return
        model = next(key for key, radio in self.radios.items() if radio.isChecked())
        options = {"timestamps": self.timestamps.isChecked(), "vad_filter": self.vad.isChecked(),
                   "initial_prompt": self.prompt.toPlainText().strip()}
        self.start_requested.emit(self.path, model, self.language.currentData(), options)


class LibraryPage(QWidget):
    new_requested = Signal()
    job_selected = Signal(str)
    delete_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("library")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.jobs = []
        self.signature = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(10)
        toolbar = QHBoxLayout()
        toolbar.addStretch()
        self.new_button = button("+", self.new_requested.emit, primary=True)
        self.new_button.setFixedSize(36, 36)
        self.new_button.setAccessibleName("새 전사")
        self.new_button.setToolTip("새 전사")
        self.new_button.setStyleSheet("padding: 0; border-radius: 18px; font-size: 23px; font-weight: 400;")
        toolbar.addWidget(self.new_button)
        layout.addLayout(toolbar)
        self.table = QTableWidget(0, 2)
        self.table.setObjectName("job-list")
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.table.setMouseTracking(True)
        self.table.setWordWrap(False)
        self.table.setAccessibleName("전사 목록")
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 185)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.table.cellClicked.connect(self.open_row)
        self.table.itemActivated.connect(lambda item: self.open_row(item.row(), item.column()))
        self.context_menu = QMenu(self.table)
        self.context_menu.setMinimumWidth(144)
        self.delete_action = self.context_menu.addAction("삭제")
        self.context_job_id = None
        self.delete_action.triggered.connect(lambda: self.delete_requested.emit(self.context_job_id))
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.table, 1)

    def set_jobs(self, jobs):
        self.jobs = jobs
        self.render()

    def render(self):
        # Preserve animated widgets and row selection during progress updates.
        jobs = self.jobs
        signature = tuple(job["id"] for job in jobs)
        if signature != self.signature:
            selected = self.table.item(self.table.currentRow(), 0)
            selected_id = selected.data(Qt.ItemDataRole.UserRole) if selected else None
            self.table.setRowCount(0)
            self.table.setRowCount(len(jobs))
            for row, job in enumerate(jobs):
                self.table.setRowHeight(row, 60)
                name = QTableWidgetItem(job["filename"])
                font = name.font()
                font.setPixelSize(14)
                name.setFont(font)
                name.setData(Qt.ItemDataRole.UserRole, job["id"])
                name.setToolTip(job["filename"])
                self.table.setItem(row, 0, name)
                self.table.setItem(row, 1, QTableWidgetItem())
                self.table.setCellWidget(row, 1, JobStatus(job))
                if job["id"] == selected_id:
                    self.table.selectRow(row)
            self.signature = signature
        for row, job in enumerate(jobs):
            self.table.cellWidget(row, 1).update_job(job)

    def open_row(self, row, column):
        item = self.table.item(row, 0)
        if item:
            self.job_selected.emit(item.data(Qt.ItemDataRole.UserRole))

    def show_context_menu(self, position):
        row = self.table.rowAt(position.y())
        if row < 0 or row >= len(self.jobs):
            return
        self.table.selectRow(row)
        job = self.jobs[row]
        self.context_job_id = job["id"]
        self.delete_action.setEnabled(job["status"] not in ACTIVE and job["status"] != "importing")
        self.context_menu.popup(self.table.viewport().mapToGlobal(position))


class StartedPage(QWidget):
    home_requested = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(60, 45, 60, 45)
        layout.setSpacing(20)
        layout.addStretch()
        layout.addWidget(WaveMark(80), alignment=Qt.AlignmentFlag.AlignHCenter)
        self.title = label("전사를 시작했어요.", "hero-title")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title)
        self.filename = label("", "subtitle", True)
        self.filename.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.filename)
        self.status = JobStatus({"status":"importing", "progress":0})
        self.status.setMaximumWidth(440)
        layout.addWidget(self.status, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.error = label("", "error", True)
        self.error.hide()
        layout.addWidget(self.error)
        copy = label("백그라운드에서 전사가 진행됩니다.\n다른 프로그램을 사용하거나 이 창을 닫아도 작업은 계속됩니다.\n메뉴 막대에서 다시 열 수 있어요.", "subtitle", True)
        copy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(copy)
        notice = label("앱을 완전히 종료하거나 컴퓨터를 잠자기 상태로 두면 작업이 중단됩니다.", "muted", True)
        notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(notice)
        layout.addSpacing(10)
        layout.addWidget(button("홈으로 돌아가기  →", self.home_requested.emit, primary=True), alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()

    def set_job(self, job):
        self.filename.setText(job["filename"])
        self.status.update_job(job)
        self.title.setText("기록이 완성되었어요." if job["status"] == "completed" else "전사를 완료하지 못했어요." if job["status"] == "failed" else "전사를 시작했어요.")
        self.error.setText(job.get("error") or "")
        self.error.setVisible(job["status"] == "failed")


class DetailPage(QWidget):
    home_requested = Signal()
    retry_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self.job = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(18)
        back = button("←  전사 목록으로", self.home_requested.emit)
        back.setProperty("compact", True)
        layout.addWidget(back, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(label("TRANSCRIPTION", "eyebrow"))
        self.title = label("", "hero-title", True)
        self.meta = label("", "muted", True)
        layout.addWidget(self.title)
        layout.addWidget(self.meta)
        self.status = JobStatus({"status":"queued", "progress":0})
        layout.addWidget(self.status)
        self.error = label("", "error", True)
        self.error.hide()
        layout.addWidget(self.error)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.addWidget(label("전사 내용", "section-title"), 1)
        self.copy_button = button("복사", self.copy_text)
        self.txt_button = button("TXT 저장", lambda: self.save("txt"))
        self.srt_button = button("SRT 저장", lambda: self.save("srt"))
        for item in [self.copy_button, self.txt_button, self.srt_button]:
            item.setProperty("compact", True)
            item.setFixedWidth(88)
            toolbar.addWidget(item)
        self.copy_button.setAccessibleName("전사 내용 복사")
        self.copy_button.setToolTip("전사 내용을 클립보드에 복사")
        self.copy_feedback = QTimer(self)
        self.copy_feedback.setSingleShot(True)
        self.copy_feedback.setInterval(1400)
        self.copy_feedback.timeout.connect(lambda: self.copy_button.setText("복사"))
        layout.addLayout(toolbar)
        self.text = QPlainTextEdit()
        self.text.setObjectName("transcript")
        self.text.setAccessibleName("전사 내용")
        self.text.setReadOnly(True)
        self.text.setPlaceholderText("전사가 진행되면 인식된 내용이 여기에 표시됩니다.")
        layout.addWidget(self.text, 1)
        footer = QHBoxLayout()
        self.delete_button = button("기록 삭제", lambda: self.delete_requested.emit(self.job["id"]))
        self.delete_button.setObjectName("danger")
        footer.addWidget(self.delete_button)
        footer.addStretch()
        self.retry_button = button("다시 전사하기", lambda: self.retry_requested.emit(self.job["id"]))
        footer.addWidget(self.retry_button)
        footer.addWidget(button("홈으로 돌아가기", self.home_requested.emit, primary=True))
        layout.addLayout(footer)

    def set_job(self, job):
        if self.job is None or self.job["id"] != job["id"]:
            self.copy_feedback.stop()
            self.copy_button.setText("복사")
        self.job = job
        self.title.setText(job["filename"])
        language = LANGUAGE_LABELS.get(job["detected_language"] or job["language"], job["detected_language"] or job["language"])
        self.meta.setText(f"{MODEL_LABELS[job['model']]} · {language} · {bytes_label(job['size'])}" + (f" · {clock_label(job['duration'])}" if job["duration"] else ""))
        self.status.update_job(job)
        self.error.setText(job["error"] or "")
        self.error.setVisible(job["status"] == "failed")
        if job["options"]["timestamps"]:
            text = "\n\n".join(f"[{clock_label(s['start'])}]  {s['text']}" for s in job["segments"])
        else:
            text = job["text"]
        if text != self.text.toPlainText():
            scroll = self.text.verticalScrollBar().value()
            self.text.setPlainText(text)
            self.text.verticalScrollBar().setValue(scroll)
        self.text.setPlaceholderText("인식된 말소리가 없습니다." if job["status"] == "completed" else "전사가 진행되면 인식된 내용이 여기에 표시됩니다.")
        completed = job["status"] == "completed"
        for item in [self.copy_button, self.txt_button, self.srt_button]:
            item.setEnabled(completed)
        self.delete_button.setEnabled(job["status"] not in ACTIVE)
        self.retry_button.setVisible(job["status"] == "failed")

    def copy_text(self):
        if self.job:
            QApplication.clipboard().setText(self.job["text"])
            self.copy_button.setText("복사됨")
            self.copy_feedback.start()

    def save(self, format_name):
        if not self.job or self.job["status"] != "completed":
            return
        filename, _ = QFileDialog.getSaveFileName(self, "전사 결과 저장", Path(self.job["filename"]).stem + "." + format_name,
                                                 f"{format_name.upper()} 파일 (*.{format_name})")
        if filename:
            try:
                Path(filename).write_text(export_text(self.job, format_name), encoding="utf-8")
            except OSError as exc:
                QMessageBox.warning(self, "저장하지 못했습니다", str(exc))


class SettingsDialog(QDialog):
    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setWindowTitle("설정")
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(18)
        layout.addWidget(label("화면 모드", "section-title"))
        self.appearance = QComboBox()
        self.appearance.setAccessibleName("화면 모드")
        self.appearance.addItem("시스템 설정 따르기 (기본값)", "system")
        self.appearance.addItem("화이트", "light")
        self.appearance.addItem("다크", "dark")
        self.appearance.setCurrentIndex(self.appearance.findData(theme.preference))
        layout.addWidget(self.appearance)
        layout.addWidget(label("변경 사항은 바로 적용되고 다음 실행에도 유지됩니다.", "muted", True))
        layout.addWidget(button("닫기", self.close), alignment=Qt.AlignmentFlag.AlignRight)
        self.appearance.currentIndexChanged.connect(self.select_mode)
        theme.changed.connect(self.sync_selection)

    def sync_selection(self):
        with QSignalBlocker(self.appearance):
            self.appearance.setCurrentIndex(self.appearance.findData(self.theme.preference))

    def select_mode(self):
        try:
            self.theme.set_mode(self.appearance.currentData())
        except OSError:
            self.sync_selection()
            QMessageBox.warning(self, "설정을 저장하지 못했습니다", "저장 폴더의 쓰기 권한을 확인해 주세요.")


class MainWindow(QMainWindow):
    imported = Signal(dict)
    import_failed = Signal(str)
    import_progress = Signal(int)

    def __init__(self, store, worker, tray_enabled=True):
        super().__init__()
        self.store = store
        self.worker = worker
        self.theme = ThemeManager(QApplication.instance(), store.directory / "settings.json", parent=self)
        self.settings_dialog = None
        self.importing = None
        self.import_stop = threading.Event()
        self.started_id = None
        self.detail_id = None
        self.detail_stamp = None
        self.quitting = False
        self.reopen_stamp = None
        self.setWindowTitle("소리노트")
        self.setMinimumSize(680, 480)
        self.resize(820, 580)
        self.setWindowIcon(app_icon())
        self.setAcceptDrops(True)
        shell = QWidget()
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        self.stack = QStackedWidget()
        self.stack.setObjectName("content")
        self.library = LibraryPage()
        self.add_page = AddPage()
        self.started_page = StartedPage()
        self.detail = DetailPage()
        for page in [self.library, self.add_page, self.started_page, self.detail]:
            self.stack.addWidget(page)
        shell_layout.addWidget(self.stack, 1)
        self.setCentralWidget(shell)
        self.library.new_requested.connect(self.show_add)
        self.library.job_selected.connect(self.show_detail)
        self.library.delete_requested.connect(self.delete)
        self.add_page.home_requested.connect(self.show_home)
        self.add_page.start_requested.connect(self.start_job)
        self.started_page.home_requested.connect(self.show_home)
        self.detail.home_requested.connect(self.show_home)
        self.detail.retry_requested.connect(self.retry)
        self.detail.delete_requested.connect(self.delete)
        self.imported.connect(self.on_imported)
        self.import_failed.connect(self.on_import_failed)
        self.import_progress.connect(self.on_import_progress)
        menu = self.menuBar().addMenu("소리노트")
        open_action = QAction("전사 목록 열기", self)
        open_action.triggered.connect(self.restore)
        menu.addAction(open_action)
        new_action = QAction("새 전사", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self.show_add)
        menu.addAction(new_action)
        self.settings_action = QAction("설정…", self)
        self.settings_action.setMenuRole(QAction.MenuRole.PreferencesRole)
        self.settings_action.setShortcut(QKeySequence.StandardKey.Preferences)
        self.settings_action.triggered.connect(self.show_settings)
        menu.addAction(self.settings_action)
        quit_action = QAction("소리노트 종료", self)
        quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.quit_application)
        menu.addAction(quit_action)
        self.tray = None
        if tray_enabled and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self.windowIcon(), self)
            self.tray.setToolTip("소리노트 · 음성을 기록으로")
            tray_menu = QMenu(self)
            tray_menu.addAction("전사 목록 열기", self.restore)
            tray_menu.addAction("새 전사", lambda: (self.restore(), self.show_add()))
            tray_menu.addAction("설정…", self.show_settings)
            tray_menu.addSeparator()
            tray_menu.addAction("소리노트 종료", self.quit_application)
            self.tray.setContextMenu(tray_menu)
            self.tray.activated.connect(self.tray_clicked)
            self.tray.show()
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.show_home()
        self.refresh()

    def show_settings(self):
        if self.settings_dialog is None:
            self.settings_dialog = SettingsDialog(self.theme, self)
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def show_home(self):
        self.stack.setCurrentWidget(self.library)
        self.detail_id = None
        self.refresh()

    def show_add(self):
        if self.importing:
            self.stack.setCurrentWidget(self.started_page)
            return
        self.add_page.reset()
        self.stack.setCurrentWidget(self.add_page)
        self.detail_id = None

    def start_job(self, path, model, language, options):
        if self.importing:
            return
        from .transcription import now
        self.importing = {"id":"importing", "filename":Path(path).name, "model":model, "language":language,
                          "status":"importing", "progress":0, "duration":0, "created_at":now()}
        self.started_id = None
        self.started_page.set_job(self.importing)
        self.stack.setCurrentWidget(self.started_page)
        self.library.new_button.setEnabled(False)

        def import_audio():
            try:
                job = self.store.add_file(path, model, language, options, self.import_progress.emit, self.import_stop)
                self.imported.emit(job)
            except Exception as exc:
                logging.exception("File import failed")
                self.import_failed.emit(str(exc))

        threading.Thread(target=import_audio, name="audio-import", daemon=True).start()
        self.refresh()

    def on_import_progress(self, value):
        if self.importing:
            self.importing["progress"] = value
            self.refresh()

    def on_imported(self, job):
        self.importing = None
        self.started_id = job["id"]
        self.library.new_button.setEnabled(True)
        self.worker.wakeup.set()
        self.started_page.set_job(job)
        self.refresh()

    def on_import_failed(self, message):
        self.importing = None
        self.library.new_button.setEnabled(True)
        self.add_page.show_error(message)
        self.stack.setCurrentWidget(self.add_page)
        self.refresh()

    def refresh(self):
        if (self.store.directory / "stop-app").exists():
            self.quit_application()
            return
        if self.quitting:
            return
        try:
            jobs = self.store.list()
            if self.importing:
                jobs = [dict(self.importing), *jobs]
            self.library.set_jobs(jobs)
            active = sum(job["status"] in ACTIVE or job["status"] == "importing" for job in jobs)
            if self.tray:
                self.tray.setToolTip(f"소리노트 · {active}개 전사 진행 중" if active else "소리노트 · 전사 라이브러리")
            if self.importing:
                self.started_page.set_job(self.importing)
            elif self.started_id:
                for job in jobs:
                    if job["id"] == self.started_id:
                        self.started_page.set_job(job)
                        break
            if self.detail_id:
                summary = next((job for job in jobs if job["id"] == self.detail_id), None)
                if summary and summary["updated_at"] != self.detail_stamp:
                    self.detail.set_job(self.store.get(self.detail_id))
                    self.detail_stamp = summary["updated_at"]
            marker = self.store.directory / "show-window"
            if marker.exists():
                stamp = marker.stat().st_mtime_ns
                if stamp != self.reopen_stamp:
                    self.reopen_stamp = stamp
                    self.restore()
        except Exception:
            logging.exception("Desktop refresh failed")
            self.library.table.setToolTip("기록을 불러오지 못했습니다. data/app.log를 확인해 주세요.")

    def show_detail(self, job_id):
        if job_id == "importing":
            self.stack.setCurrentWidget(self.started_page)
            return
        try:
            job = self.store.get(job_id)
            self.detail_id = job_id
            self.detail_stamp = job["updated_at"]
            self.detail.set_job(job)
            self.stack.setCurrentWidget(self.detail)
        except AppError as exc:
            QMessageBox.warning(self, "기록 확인", str(exc))

    def retry(self, job_id):
        try:
            self.store.retry(job_id)
            self.worker.wakeup.set()
            self.detail_stamp = None
            self.refresh()
        except AppError as exc:
            QMessageBox.warning(self, "다시 전사하기", str(exc))

    def delete(self, job_id):
        answer = QMessageBox.question(self, "기록 삭제", "이 전사 기록과 프로그램 내부 음성 사본을 삭제할까요?\n원래 음성 파일은 유지됩니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.delete(job_id)
            if self.started_id == job_id:
                self.started_id = None
            self.show_home()
        except (AppError, OSError) as exc:
            QMessageBox.warning(self, "기록 삭제", str(exc))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.importing:
            event.acceptProposedAction()

    def dropEvent(self, event):
        if self.importing:
            return
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        self.show_add()
        if len(paths) == 1:
            self.add_page.select_file(paths[0])
            event.acceptProposedAction()
        else:
            self.add_page.show_error("한 번에 하나의 음성 파일을 추가해 주세요.")

    def tray_clicked(self, reason):
        if reason in {QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick}:
            self.restore()

    def restore(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        if self.quitting:
            event.accept()
            return
        event.ignore()
        if self.settings_dialog:
            self.settings_dialog.hide()
        self.hide()
        if self.tray:
            self.tray.showMessage("소리노트", "창을 닫아도 전사는 계속됩니다. 메뉴 막대에서 다시 열거나 종료할 수 있습니다.")

    def quit_application(self):
        self.quitting = True
        self.timer.stop()
        self.import_stop.set()
        self.worker.stopping.set()
        self.worker.wakeup.set()
        if self.tray:
            self.tray.hide()
        QApplication.instance().quit()


class DesktopApplication(QApplication):
    def __init__(self, args):
        self.window = None
        super().__init__(args)

    def event(self, event):
        if event.type() == QEvent.Type.ApplicationActivate and self.window and not self.window.quitting and self.window.isHidden():
            self.window.restore()
        return super().event(event)


def main():
    parser = argparse.ArgumentParser(description="소리노트 데스크톱 GUI")
    parser.add_argument("--data-dir", type=Path, default=data_directory())
    args = parser.parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    lock = InstanceLock(args.data_dir)
    if not lock.acquire():
        (args.data_dir / "show-window").write_text(str(os.getpid()))
        lock.close()
        return
    (args.data_dir / "stop-app").unlink(missing_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(args.data_dir / "app.log", encoding="utf-8")])
    application = DesktopApplication(sys.argv[:1])
    application.setApplicationName("소리노트")
    application.setOrganizationName("Soundnote")
    application.setFont(QFont("Malgun Gothic" if sys.platform == "win32" else "Apple SD Gothic Neo", 13))
    application.setStyle("Fusion")
    application.setWindowIcon(app_icon())
    application.setQuitOnLastWindowClosed(False)
    store = Store(args.data_dir)
    worker = Worker(store)
    worker.start()
    window = MainWindow(store, worker)
    application.window = window
    window.show()
    runtime = args.data_dir / "desktop-runtime.json"
    runtime.write_text(json.dumps({"app":"soundnote-desktop", "pid":os.getpid(), "workspace":str(ROOT)}), encoding="utf-8")
    signal.signal(signal.SIGTERM, lambda *_: window.quit_application())
    signal.signal(signal.SIGINT, lambda *_: window.quit_application())
    try:
        application.exec()
    finally:
        worker.stop()
        window.import_stop.set()
        runtime.unlink(missing_ok=True)
        (args.data_dir / "show-window").unlink(missing_ok=True)
        (args.data_dir / "stop-app").unlink(missing_ok=True)
        lock.close()


if __name__ == "__main__":
    main()
