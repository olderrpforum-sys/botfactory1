# BotFactory — single-file app.py (PyQt6 + Telethon)
# Requires: Python 3.11, pip install -r requirements.txt
import os
import sys
import re
import csv
import json
import asyncio
import time
import zipfile
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, List, Dict, Tuple

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QTimer, QSize, QPoint, QPointF, QRect, QPropertyAnimation, QEasingCurve, QUrl
from PyQt6.QtGui import QColor, QPainter, QPixmap, QIcon, QFont, QLinearGradient, QPen, QBrush, QDesktopServices
from PyQt6.QtWidgets import (
    QTextBrowser,
    QPlainTextEdit,
    QScrollArea,
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QFrame,
    QFileDialog,
    QStackedWidget,
    QComboBox,
    QSpinBox,
    QCheckBox,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QListView,
    QDialog,
    QFormLayout,
    QSizePolicy,
    QGraphicsDropShadowEffect,
    QInputDialog,
    QGraphicsOpacityEffect,
    QToolButton,
    QMenu
)

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from telethon.tl.functions.messages import SendMessageRequest

APP_NAME = "BotFactory"
BYLINE = "by whynot"

BASE_DIR = Path(__file__).resolve().parent
SESSIONS_DIR = BASE_DIR / "sessions"
ACCOUNTS_FILE = BASE_DIR / "accounts_tg.txt"
CONFIG_FILE = BASE_DIR / "config.json"
HAMSTERS_FILE = BASE_DIR / "hamsters.json"
FROZEN_FILE = BASE_DIR / "frozen.json"
ACCOUNTS_STATUS_FILE = BASE_DIR / "accounts_status.json"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

BOTFATHER_USERNAME_DEFAULT = "BotFather"

def parse_accounts(path: Path) -> List[Dict]:
    accs = []
    if not path.exists():
        return accs
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) < 4:
            continue
        phone, pwd, api_id, api_hash = parts[:4]
        try:
            parsed_api_id = int(api_id.strip())
        except ValueError:
            continue
        accs.append({
            "phone": phone.strip(),
            "password": None if pwd.strip().upper() == "UNKNOWN" else pwd.strip(),
            "api_id": parsed_api_id,
            "api_hash": api_hash.strip(),
        })
    return accs

def ensure_file(path: Path):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

def safe_int(s: str, default: int = 0) -> int:
    try:
        return int(s)
    except:
        return default

def extract_try_again_seconds(text: str) -> Optional[int]:
    m = re.search(r"Please try again in (\d+) seconds", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None

def extract_token(text: str) -> Optional[str]:
    # Robust: BotFather token is like 123456789:AA... (base64url-ish)
    m = re.search(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b", text or "")
    return m.group(0) if m else None

def has_too_many_bots(text: str) -> bool:
    return "can't add more than 20 bots" in (text or "").lower()
def sanitize_base(base: str) -> str:
    b = base.lower()
    b = re.sub(r"[^a-z0-9_]", "", b)
    b = re.sub(r"_+", "_", b).strip("_")
    return b or "bot"

def center_on_screen(w: QWidget):
    screen = QApplication.primaryScreen()
    if not screen:
        return
    geo = screen.availableGeometry()
    x = geo.x() + (geo.width() - w.width()) // 2
    y = geo.y() + (geo.height() - w.height()) // 2
    w.move(x, y)

def apply_shadow(widget: QWidget, blur: int = 24, alpha: int = 160, offset: QPointF = QPointF(0, 6)):
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setColor(QColor(0, 0, 0, alpha))
    shadow.setOffset(offset)
    widget.setGraphicsEffect(shadow)

def configure_table(widget):
    try:
        widget.setFrameShape(QFrame.Shape.NoFrame)
    except Exception:
        pass
    try:
        widget.setCornerButtonEnabled(False)
    except Exception:
        pass
    try:
        widget.setShowGrid(True)
    except Exception:
        pass
    try:
        widget.verticalHeader().setVisible(False)
    except Exception:
        pass
    try:
        widget.setAlternatingRowColors(True)
    except Exception:
        pass
    try:
        pal = widget.palette()
        pal.setColor(pal.ColorRole.Base, QColor(10, 16, 30))
        pal.setColor(pal.ColorRole.AlternateBase, QColor(14, 20, 36))
        pal.setColor(pal.ColorRole.Text, QColor(230, 237, 243))
        widget.setPalette(pal)
    except Exception:
        pass
    try:
        widget.horizontalHeader().setStretchLastSection(True)
    except Exception:
        pass
    try:
        widget.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    except Exception:
        pass
    try:
        widget.setTextElideMode(Qt.TextElideMode.ElideRight)
    except Exception:
        pass
    try:
        widget.setWordWrap(False)
    except Exception:
        pass

def animate_fade(widget: QWidget, start: float = 0.0, end: float = 1.0, duration: int = 260):
    if widget is None:
        return
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    effect.setOpacity(start)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setDuration(duration)
    anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

def animate_section_fade(widget: QWidget, duration: int = 220):
    if widget is None:
        return
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    effect.setOpacity(0.0)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setDuration(duration)
    anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
    def _cleanup():
        widget.setGraphicsEffect(None)
    anim.finished.connect(_cleanup)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

def animate_button_press(btn: QWidget, duration: int = 160):
    if btn is None or not btn.isVisible():
        return
    effect = btn.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(btn)
        btn.setGraphicsEffect(effect)
    effect.setOpacity(1.0)
    anim = QPropertyAnimation(effect, b"opacity", btn)
    anim.setStartValue(1.0)
    anim.setKeyValueAt(0.5, 0.82)
    anim.setEndValue(1.0)
    anim.setDuration(duration)
    anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
    def _cleanup():
        btn.setGraphicsEffect(None)
    anim.finished.connect(_cleanup)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

def animate_evaporate_rect(parent: QWidget, rect: QRect, on_done=None):
    if parent is None or rect.isNull():
        if on_done:
            on_done()
        return
    overlay = QFrame(parent)
    overlay.setStyleSheet("background: rgba(120, 160, 255, 0.20); border-radius: 10px;")
    overlay.setGeometry(rect)
    overlay.show()
    effect = QGraphicsOpacityEffect(overlay)
    overlay.setGraphicsEffect(effect)
    effect.setOpacity(1.0)
    fade = QPropertyAnimation(effect, b"opacity", overlay)
    fade.setStartValue(1.0)
    fade.setKeyValueAt(0.65, 0.55)
    fade.setEndValue(0.0)
    fade.setDuration(320)
    fade.setEasingCurve(QEasingCurve.Type.InOutCubic)
    shrink = QPropertyAnimation(overlay, b"geometry", overlay)
    shrink.setStartValue(rect)
    target = QRect(rect.center().x(), rect.center().y(), 2, 2)
    shrink.setEndValue(target)
    shrink.setDuration(320)
    shrink.setEasingCurve(QEasingCurve.Type.InOutCubic)
    glow = QPropertyAnimation(overlay, b"windowOpacity", overlay)
    glow.setStartValue(1.0)
    glow.setKeyValueAt(0.5, 0.85)
    glow.setEndValue(0.0)
    glow.setDuration(320)
    glow.setEasingCurve(QEasingCurve.Type.InOutCubic)
    def _finish():
        overlay.deleteLater()
        if on_done:
            on_done()
    fade.finished.connect(_finish)
    fade.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    shrink.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    glow.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

def animate_press(widget: QWidget, duration: int = 120, delta: int = 2):
    if widget is None or not widget.isVisible():
        return
    geo = widget.geometry()
    target = geo.adjusted(delta, delta, -delta, -delta)
    anim = QPropertyAnimation(widget, b"geometry", widget)
    anim.setDuration(duration)
    anim.setKeyValueAt(0.0, geo)
    anim.setKeyValueAt(0.5, target)
    anim.setKeyValueAt(1.0, geo)
    anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

class ActionAnimator(QObject):
    def eventFilter(self, obj, event):
        if event.type() == event.Type.MouseButtonPress and isinstance(obj, (QPushButton, QToolButton)):
            animate_button_press(obj)
        return super().eventFilter(obj, event)

def show_message(parent: QWidget, title: str, text: str):
    dlg = StyledDialog(parent, title)
    dlg.resize(560, 240)
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName("Hint")

    ok = QPushButton("ОК")
    ok.setObjectName("PrimaryBtn")
    ok.clicked.connect(dlg.accept)

    row = QHBoxLayout()
    row.addStretch(1)
    row.addWidget(ok)

    body = QVBoxLayout()
    body.addWidget(label)
    body.addLayout(row)
    dlg.set_body_layout(body)
    dlg.exec()

def show_copy_dialog(parent: QWidget, title: str, text: str, copy_text: str):
    dlg = StyledDialog(parent, title)
    dlg.resize(640, 360)

    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName("Hint")

    box = QPlainTextEdit()
    box.setObjectName("Input")
    box.setReadOnly(True)
    box.setPlainText(copy_text)

    copy_btn = QPushButton("Скопировать")
    copy_btn.setObjectName("SecondaryBtn")
    ok = QPushButton("ОК")
    ok.setObjectName("PrimaryBtn")

    row = QHBoxLayout()
    row.addStretch(1)
    row.addWidget(copy_btn)
    row.addWidget(ok)

    body = QVBoxLayout()
    body.addWidget(label)
    body.addWidget(box, 1)
    body.addLayout(row)
    dlg.set_body_layout(body)

    def _copy():
        QApplication.clipboard().setText(copy_text)
    copy_btn.clicked.connect(_copy)
    ok.clicked.connect(dlg.accept)
    dlg.exec()

def show_input_dialog(parent: QWidget, title: str, prompt: str, placeholder: str = "", echo_mode: QLineEdit.EchoMode = QLineEdit.EchoMode.Normal) -> Optional[str]:
    dlg = StyledDialog(parent, title)
    dlg.resize(560, 260)

    label = QLabel(prompt)
    label.setWordWrap(True)
    label.setObjectName("Hint")

    entry = QLineEdit()
    entry.setObjectName("Input")
    entry.setPlaceholderText(placeholder)
    entry.setEchoMode(echo_mode)

    ok = QPushButton("ОК"); ok.setObjectName("PrimaryBtn")
    cancel = QPushButton("Отмена"); cancel.setObjectName("SecondaryBtn")

    row = QHBoxLayout()
    row.addWidget(ok); row.addWidget(cancel); row.addStretch(1)

    body = QVBoxLayout()
    body.addWidget(label)
    body.addWidget(entry)
    body.addLayout(row)
    dlg.set_body_layout(body)

    ok.clicked.connect(dlg.accept)
    cancel.clicked.connect(dlg.reject)

    if dlg.exec() == QDialog.DialogCode.Accepted:
        return entry.text().strip()
    return None

def show_multiline_dialog(parent: QWidget, title: str, prompt: str, placeholder: str = "") -> Optional[str]:
    dlg = StyledDialog(parent, title)
    dlg.resize(620, 360)

    label = QLabel(prompt)
    label.setWordWrap(True)
    label.setObjectName("Hint")

    entry = QPlainTextEdit()
    entry.setObjectName("Input")
    entry.setPlaceholderText(placeholder)

    ok = QPushButton("ОК"); ok.setObjectName("PrimaryBtn")
    cancel = QPushButton("Отмена"); cancel.setObjectName("SecondaryBtn")

    row = QHBoxLayout()
    row.addWidget(ok); row.addWidget(cancel); row.addStretch(1)

    body = QVBoxLayout()
    body.addWidget(label)
    body.addWidget(entry)
    body.addLayout(row)
    dlg.set_body_layout(body)

    ok.clicked.connect(dlg.accept)
    cancel.clicked.connect(dlg.reject)

    if dlg.exec() == QDialog.DialogCode.Accepted:
        return entry.toPlainText().strip()
    return None

def load_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except:
        pass
    return default

def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

@dataclass
class AutoConfig:
    botfather: str = BOTFATHER_USERNAME_DEFAULT
    name_prefix: str = "ОРИГ С ТТ❤️"
    name_suffix: str = ""
    username_suffix: str = "_bot"
    numbered_separator: str = "_"
    numbered_suffix: str = "bot"
    max_number_attempts: int = 5
    sanitize_username: bool = True
    tokens_txt: str = "tokens.txt"
    tokens_csv: str = "tokens.csv"
    revoked_tokens_txt: str = "revoked_tokens.txt"
    per_account_limit: int = 2
    freeze_threshold_seconds: int = 350
    force_setuserpic_delay1: float = 1.0
    force_setuserpic_delay2: float = 1.0
    first_run_done: bool = False
    language: str = "Русский"

    def tokens_txt_path(self) -> Path:
        p = Path(self.tokens_txt)
        return p if p.is_absolute() else BASE_DIR / p

    def tokens_csv_path(self) -> Path:
        p = Path(self.tokens_csv)
        return p if p.is_absolute() else BASE_DIR / p

    def revoked_tokens_txt_path(self) -> Path:
        p = Path(self.revoked_tokens_txt)
        return p if p.is_absolute() else BASE_DIR / p

class PromptBridge(QObject):
    request_code = pyqtSignal(str)
    request_password = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._code = ""
        self._pwd = ""
        self._ev_code = asyncio.Event()
        self._ev_pwd = asyncio.Event()

    async def get_code(self, phone: str) -> str:
        self._code = ""
        self._ev_code = asyncio.Event()
        self.request_code.emit(phone)
        await self._ev_code.wait()
        return self._code

    async def get_password(self, phone: str) -> str:
        self._pwd = ""
        self._ev_pwd = asyncio.Event()
        self.request_password.emit(phone)
        await self._ev_pwd.wait()
        return self._pwd

    def set_code(self, code: str):
        self._code = code.strip()
        self._ev_code.set()

    def set_password(self, pwd: str):
        self._pwd = pwd
        self._ev_pwd.set()

def neon_icon(kind: str, size: int = 14) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    grad = QColor(120, 60, 255)
    grad2 = QColor(0, 200, 255)
    p.setBrush(grad)
    p.drawRoundedRect(0, 0, size, size, 4, 4)
    p.setBrush(grad2)
    p.setOpacity(0.55)
    p.drawRoundedRect(0, 0, size, size, 4, 4)
    p.setOpacity(1.0)
    if kind == "min":
        p.setBrush(QColor(255,255,255,220))
        p.drawRoundedRect(3, size-5, size-6, 2, 1, 1)
    elif kind == "max":
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QColor(255,255,255,230))
        p.drawRoundedRect(4, 4, size-8, size-8, 2, 2)
    elif kind == "close":
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QColor(255,255,255,230))
        p.drawLine(4,4,size-4,size-4)
        p.drawLine(size-4,4,4,size-4)
    p.end()
    return QIcon(pm)

class PremiumTitleBar(QFrame):
    def __init__(self, parent: QMainWindow, title: str):
        super().__init__(parent)
        self._win = parent
        self.setObjectName("PremiumTitleBar")
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(10)

        self.title_lbl = QLabel(title)
        self.title_lbl.setObjectName("TitleBarText")
        lay.addWidget(self.title_lbl)
        lay.addStretch(1)

        btn_wrap = QWidget()
        btn_wrap.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        btn_lay = QHBoxLayout(btn_wrap)
        btn_lay.setContentsMargins(0, 0, 0, 0)
        btn_lay.setSpacing(10)

        self.btn_min = QPushButton("")
        self.btn_min.setObjectName("WinBtn")
        self.btn_min.setIcon(neon_icon("min", 14))
        self.btn_min.setIconSize(QSize(14,14))
        self.btn_min.setFixedSize(38, 28)

        self.btn_max = QPushButton("")
        self.btn_max.setObjectName("WinBtn")
        self.btn_max.setIcon(neon_icon("max", 14))
        self.btn_max.setIconSize(QSize(14,14))
        self.btn_max.setFixedSize(38, 28)

        self.btn_close = QPushButton("")
        self.btn_close.setObjectName("WinClose")
        self.btn_close.setIcon(neon_icon("close", 14))
        self.btn_close.setIconSize(QSize(14,14))
        self.btn_close.setFixedSize(38, 28)

        self.btn_min.clicked.connect(self._win.showMinimized)
        self.btn_max.clicked.connect(self._toggle_max)
        self.btn_close.clicked.connect(self._win.close)

        btn_lay.addWidget(self.btn_min)
        btn_lay.addWidget(self.btn_max)
        btn_lay.addWidget(self.btn_close)
        lay.addWidget(btn_wrap, 0, Qt.AlignmentFlag.AlignRight)

        self._drag_pos: Optional[QPoint] = None

    def _toggle_max(self):
        if self._win.isMaximized():
            self._win.showNormal()
        else:
            self._win.showMaximized()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag_pos and (e.buttons() & Qt.MouseButton.LeftButton):
            delta = e.globalPosition().toPoint() - self._drag_pos
            self._win.move(self._win.pos() + delta)
            self._drag_pos = e.globalPosition().toPoint()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None
        super().mouseReleaseEvent(e)

class StyledDialog(QDialog):
    def __init__(self, parent: QWidget, title: str):
        super().__init__(parent)
        self.setObjectName("StyledDialog")
        self.setObjectName("PremiumDialog")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0)

        self.card = QFrame()
        self.card.setObjectName("PremiumDialogCard")
        outer.addWidget(self.card)

        try:
            eff = QGraphicsDropShadowEffect(self.card)
            eff.setBlurRadius(28)
            eff.setOffset(0, 10)
            eff.setColor(QColor(0, 0, 0, 170))
            self.card.setGraphicsEffect(eff)
        except Exception:
            pass

        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(18, 14, 18, 16)
        lay.setSpacing(12)

        bar = QHBoxLayout()
        lbl = QLabel(title)
        lbl.setObjectName("PremiumDialogTitle")
        bar.addWidget(lbl)
        bar.addStretch(1)

        btn_close = QPushButton("")
        btn_close.setObjectName("WinClose")
        btn_close.setIcon(neon_icon("close", 14))
        btn_close.setIconSize(QSize(14,14))
        btn_close.setFixedSize(38, 28)
        btn_close.clicked.connect(self.reject)
        bar.addWidget(btn_close)

        lay.addLayout(bar)

        self.body = QVBoxLayout()
        self.body.setSpacing(12)
        lay.addLayout(self.body)

        self._drag_pos: Optional[QPoint] = None

    def showEvent(self, event):
        super().showEvent(event)
        animate_fade(self.card, 0.0, 1.0, 160)

    def set_body_layout(self, layout: QVBoxLayout):
        while self.body.count():
            item = self.body.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                item.layout().deleteLater()
        self.body.addLayout(layout)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag_pos and (e.buttons() & Qt.MouseButton.LeftButton):
            delta = e.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = e.globalPosition().toPoint()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None
        super().mouseReleaseEvent(e)

class FirstRunDialog(QDialog):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("FirstRunDialog")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(720, 360)
        self.selected_language = "Русский"
        self.launch_onboarding = True

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.card = QFrame()
        self.card.setObjectName("FirstRunCard")
        apply_shadow(self.card, blur=28, alpha=180, offset=QPointF(0, 8))
        card_lay = QVBoxLayout(self.card)
        card_lay.setContentsMargins(24, 22, 24, 22)
        card_lay.setSpacing(14)

        title = QLabel("Добро пожаловать в BotFactory!")
        title.setObjectName("OverlayTitle")
        subtitle = QLabel("Давайте настроим приложение под вас. Это меню показывается только один раз.")
        subtitle.setWordWrap(True)
        subtitle.setObjectName("Hint")

        lang_row = QHBoxLayout()
        lang_lbl = QLabel("Язык приложения:")
        lang_lbl.setObjectName("Hint")
        self.lang = QComboBox()
        self.lang.setObjectName("Input")
        self.lang.addItems(["Русский", "English"])
        self.lang.currentTextChanged.connect(self._on_lang)
        lang_row.addWidget(lang_lbl)
        lang_row.addWidget(self.lang, 1)

        self.onboarding_check = QCheckBox("Запустить мастер новичка после входа")
        self.onboarding_check.setChecked(True)
        self.onboarding_check.stateChanged.connect(self._on_onboarding_toggle)

        btn_row = QHBoxLayout()
        start = QPushButton("Продолжить")
        start.setObjectName("PrimaryBtn")
        start.clicked.connect(self.accept)
        btn_row.addStretch(1)
        btn_row.addWidget(start)

        card_lay.addWidget(title)
        card_lay.addWidget(subtitle)
        card_lay.addLayout(lang_row)
        card_lay.addWidget(self.onboarding_check)
        card_lay.addLayout(btn_row)

        outer.addStretch(1)
        outer.addWidget(self.card)
        outer.addStretch(1)

    def _on_lang(self, text: str):
        self.selected_language = text

    def _on_onboarding_toggle(self, state: int):
        self.launch_onboarding = state == Qt.CheckState.Checked

    def showEvent(self, event):
        super().showEvent(event)
        animate_fade(self.card, 0.0, 1.0, 180)

class OnboardingOverlay(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("OnboardingOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.steps = []
        self.step_index = 0
        self.on_step_changed = None
        self.target_widget: Optional[QWidget] = None
        self._last_target: Optional[QWidget] = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(12)

        lay.addStretch(1)
        self.card = QFrame()
        self.card.setObjectName("OverlayCard")
        apply_shadow(self.card, blur=30, alpha=180, offset=QPointF(0, 8))
        card_lay = QVBoxLayout(self.card)
        card_lay.setContentsMargins(28, 24, 28, 24)
        card_lay.setSpacing(16)

        self.title = QLabel("")
        self.title.setObjectName("OverlayTitle")
        self.title.setMinimumHeight(28)
        self.text = QLabel("")
        self.text.setWordWrap(True)
        self.text.setObjectName("OverlayText")
        self.text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.text.setMinimumWidth(520)
        self.text.setMinimumHeight(140)
        self.text.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.text.setTextFormat(Qt.TextFormat.PlainText)
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        nav = QHBoxLayout()
        nav.setSpacing(12)
        nav.setContentsMargins(0, 8, 0, 0)
        self.back = QPushButton("Назад")
        self.back.setObjectName("SecondaryBtn")
        self.next = QPushButton("Далее")
        self.next.setObjectName("PrimaryBtn")
        self.close_btn = QPushButton("Закрыть")
        self.close_btn.setObjectName("SecondaryBtn")
        for btn in (self.back, self.next, self.close_btn):
            btn.setMinimumWidth(120)
            btn.setFixedHeight(36)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        nav.addWidget(self.back)
        nav.addWidget(self.next)
        nav.addStretch(1)
        nav.addWidget(self.close_btn)

        self.back.clicked.connect(self.prev_step)
        self.next.clicked.connect(self.next_step)
        self.close_btn.clicked.connect(self.close_overlay)

        card_lay.addWidget(self.title)
        card_lay.addWidget(self.text)
        card_lay.addLayout(nav)
        lay.addWidget(self.card, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addStretch(1)

    def set_target_widget(self, widget: Optional[QWidget]):
        if self._last_target is not None:
            self._last_target.setProperty("onboarding", "false")
            self._last_target.style().unpolish(self._last_target)
            self._last_target.style().polish(self._last_target)
        self.target_widget = widget
        self._last_target = widget
        if widget is not None:
            widget.setProperty("onboarding", "true")
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def set_steps(self, steps: List[Tuple[str, str]]):
        self.steps = steps
        self.step_index = 0
        self._apply_step()

    def _apply_step(self):
        if not self.steps:
            return
        title, body = self.steps[self.step_index]
        try:
            self.text.setGraphicsEffect(None)
            self.title.setGraphicsEffect(None)
        except Exception:
            pass
        self.title.setText(title)
        self.text.setText(body)
        self.text.adjustSize()
        self.back.setEnabled(self.step_index > 0)
        self.next.setText("Готово" if self.step_index >= len(self.steps) - 1 else "Далее")
        animate_fade(self.text, 1.0, 1.0, 1)
        animate_fade(self.title, 1.0, 1.0, 1)
        self.text.setGraphicsEffect(None)
        self.title.setGraphicsEffect(None)
        if callable(self.on_step_changed):
            self.on_step_changed(self.step_index)

    def next_step(self):
        if self.step_index >= len(self.steps) - 1:
            self.close_overlay()
            return
        self.step_index += 1
        self._apply_step()

    def prev_step(self):
        if self.step_index <= 0:
            return
        self.step_index -= 1
        self._apply_step()

    def open_overlay(self):
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setGeometry(self.parentWidget().rect())
        self.show()
        animate_fade(self.card, 0.0, 1.0, 180)

    def close_overlay(self):
        if self._last_target is not None:
            self._last_target.setProperty("onboarding", "false")
            self._last_target.style().unpolish(self._last_target)
            self._last_target.style().polish(self._last_target)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.hide()
        self.move(0, 0)
        self.setGeometry(self.parentWidget().rect())

class LogBox(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("LogBox")
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(0)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setObjectName("LogText")

        # Force dark log forever (Windows themes can't override this)
        _LOG_QSS = """QPlainTextEdit {
            background-color: rgba(10,16,30,0.90);
            color: rgba(230,237,243,0.94);
            border: 1px solid rgba(120,160,255,0.20);
            border-radius: 18px;
            padding: 14px 16px;
            font-weight: 700;
        }
        QPlainTextEdit:focus {
            border: 1px solid rgba(120,160,255,0.40);
        }
        QPlainTextEdit QScrollBar:vertical {
            background: transparent;
            width: 10px;
            margin: 8px 6px 8px 0px;
        }
        QPlainTextEdit QScrollBar::handle:vertical {
            background: rgba(120,160,255,0.35);
            border-radius: 5px;
            min-height: 40px;
        }
        QPlainTextEdit QScrollBar::add-line:vertical,
        QPlainTextEdit QScrollBar::sub-line:vertical { height: 0px; }
        """
        try:
            self.text.setStyleSheet(_LOG_QSS)
        except Exception:
            pass
        try:
            from PyQt6.QtGui import QColor
            pal = self.text.palette()
            pal.setColor(pal.ColorRole.Base, QColor(10,16,30))
            pal.setColor(pal.ColorRole.Text, QColor(230,237,243))
            self.text.setPalette(pal)
            self.text.setAutoFillBackground(False)
        except Exception:
            pass
        self.text.setFrameShape(QFrame.Shape.NoFrame)
        self.text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text.setMaximumHeight(220)
        self.text.setMinimumHeight(140)
        self.text.setPlaceholderText("Логи появятся здесь…")

        lay.addWidget(self.text)

    def append(self, s: str):
        # Do not resize the UI: log area is scrollable and has fixed max height
        self.text.appendPlainText(s)
        sb = self.text.verticalScrollBar()
        sb.setValue(sb.maximum())
        animate_fade(self.text, 0.85, 1.0, 180)

class Worker(QThread):

    log = pyqtSignal(str)
    progress = pyqtSignal(str)
    finished_ok = pyqtSignal()

    def __init__(self, mode: str, chat: str, names: List[str], hamster: str,
                 image_path: str, cfg: AutoConfig, bridge: PromptBridge, overrides: Optional[Dict[str, Dict]] = None,
                 account_status: Optional[Dict[str, Dict]] = None,
                 delete_targets: Optional[List[Dict[str, str]]] = None,
                 revoke_targets: Optional[List[Dict[str, str]]] = None):
        super().__init__()
        self.mode = mode
        self.chat = chat
        self.names = names
        self.hamster = hamster
        self.image_path = image_path
        self.cfg = cfg
        self.bridge = bridge
        self.overrides = overrides or {}
        self.account_status = account_status or {}
        self.delete_targets = delete_targets or []
        self.revoke_targets = revoke_targets or []
        self.too_many_phones: set[str] = set()
        self.no_available_accounts = False
        self.remaining_names: List[str] = []
        self.revoked_results: List[Tuple[str, str]] = []
        self.stop_requested = False

    def stop(self):
        self.stop_requested = True

    def run(self):
        asyncio.run(self._run_async())
        self.finished_ok.emit()

    async def _ensure_auth(self, client: TelegramClient, acc: Dict):
        if await client.is_user_authorized():
            return
        await client.send_code_request(acc["phone"])
        code = await self.bridge.get_code(acc["phone"])
        await client.sign_in(acc["phone"], code)
        if acc.get("password"):
            try:
                await client.sign_in(password=acc["password"])
            except SessionPasswordNeededError:
                pwd = await self.bridge.get_password(acc["phone"])
                if pwd:
                    await client.sign_in(password=pwd)

    async def _wait_rate(self, seconds: int):
        self.log.emit(f"[RATE] Ждём {seconds} сек...")
        for _ in range(seconds):
            if self.stop_requested:
                return
            await asyncio.sleep(1)

    def _build_bot_name(self, base: str) -> str:
        override = self.overrides.get(base, {})
        prefix = override.get("name_prefix", self.cfg.name_prefix)
        suffix = override.get("name_suffix", self.cfg.name_suffix)
        return f"{prefix}{base}{suffix}"

    def _build_username_candidates(self, base: str) -> List[str]:
        override = self.overrides.get(base, {})
        sanitize = override.get("sanitize_username", self.cfg.sanitize_username)
        b = sanitize_base(base) if sanitize else base
        user_suffix = override.get("username_suffix", self.cfg.username_suffix)
        sep = override.get("numbered_separator", self.cfg.numbered_separator)
        num_suffix = override.get("numbered_suffix", self.cfg.numbered_suffix)
        max_attempts = override.get("max_number_attempts", self.cfg.max_number_attempts)
        candidates = [f"{b}{user_suffix}"]
        for n in range(1, max_attempts + 1):
            candidates.append(f"{b}{sep}{n}{num_suffix}")
        return candidates

    async def _send_rate_aware(self, client: TelegramClient, peer: str, text: str) -> Tuple[bool, str]:
        await client(SendMessageRequest(peer, text))
        await asyncio.sleep(0.8)
        last = await client.get_messages(peer, limit=1)
        resp = last[0].text if last else ""
        sec = extract_try_again_seconds(resp)
        if sec:
            return False, resp
        return True, resp

    async def _wait_for_new_message(self, client: TelegramClient, peer: str, last_id: int, timeout: float = 20.0) -> Optional[str]:
        started = time.time()
        while time.time() - started < timeout:
            if self.stop_requested:
                return None
            msgs = await client.get_messages(peer, limit=6)
            new_msgs = [m for m in reversed(msgs) if getattr(m, "id", 0) > last_id]
            if new_msgs:
                texts = []
                for m in new_msgs:
                    txt = (getattr(m, "raw_text", "") or getattr(m, "message", "") or "")
                    if txt:
                        texts.append(txt)
                return "\n".join(texts) if texts else ""
            await asyncio.sleep(0.6)
        return None

    async def _wait_for_message_contains(
        self,
        client: TelegramClient,
        peer: str,
        last_id: int,
        phrases: List[str],
        timeout: float = 35.0
    ) -> Optional[str]:
        started = time.time()
        expect = [p.lower() for p in phrases]
        current_last = last_id
        while time.time() - started < timeout:
            if self.stop_requested:
                return None
            msgs = await client.get_messages(peer, limit=10)
            found = False
            for m in reversed(msgs):
                mid = getattr(m, "id", 0)
                if mid <= current_last:
                    continue
                current_last = max(current_last, mid)
                txt = (getattr(m, "raw_text", "") or getattr(m, "message", "") or "")
                if not txt:
                    continue
                lowered = txt.lower()
                if any(p in lowered for p in expect):
                    return txt
                found = True
            if found:
                await asyncio.sleep(0.6)
            else:
                await asyncio.sleep(0.6)
        return None

    async def _create_one_bot(self, client: TelegramClient, base_name: str) -> Optional[Tuple[str, str]]:
        peer = self.chat

        last = await client.get_messages(peer, limit=1)
        last_id = last[0].id if last else 0
        await client(SendMessageRequest(peer, "/start"))
        await self._wait_for_new_message(client, peer, last_id, timeout=12.0)

        last = await client.get_messages(peer, limit=1)
        last_id = last[0].id if last else 0
        await client(SendMessageRequest(peer, "/newbot"))
        start_prompt = await self._wait_for_message_contains(
            client,
            peer,
            last_id,
            ["Alright, a new bot", "please choose a name for your bot"],
            timeout=25.0
        )
        if not start_prompt:
            self.log.emit("[WARN] Нет запроса имени от BotFather. (Возможно лимит 20 ботов")
            return None
        if has_too_many_bots(start_prompt):
            self.account_status[self.current_phone] = {"state": "too_many", "reason": "20+"}
            self.too_many_phones.add(self.current_phone)
            try:
                save_json(ACCOUNTS_STATUS_FILE, self.account_status)
            except Exception:
                pass
            return None

        last = await client.get_messages(peer, limit=1)
        last_id = last[0].id if last else 0
        await client(SendMessageRequest(peer, self._build_bot_name(base_name)))
        name_prompt = await self._wait_for_message_contains(
            client,
            peer,
            last_id,
            ["choose a username for your bot", "it must end in", "username for your bot"],
            timeout=25.0
        )
        if not name_prompt:
            self.log.emit("[WARN] Нет запроса username от BotFather. (Возможно лимит 20 ботов")
            return None

        for uname in self._build_username_candidates(base_name):
            if self.stop_requested:
                return None
            last = await client.get_messages(peer, limit=1)
            last_id = last[0].id if last else 0
            await client(SendMessageRequest(peer, uname))
            joined = await self._wait_for_new_message(client, peer, last_id, timeout=25.0)
            if joined is None:
                self.log.emit("[WARN] Нет ответа BotFather — переходим к следующему username.")
                continue

            sec = extract_try_again_seconds(joined)
            if sec:
                if sec > self.cfg.freeze_threshold_seconds:
                    return None
                await self._wait_rate(sec + 1)
                continue

            if has_too_many_bots(joined):
                self.account_status[self.current_phone] = {"state": "too_many", "reason": "20+"}
                self.too_many_phones.add(self.current_phone)
                try:
                    save_json(ACCOUNTS_STATUS_FILE, self.account_status)
                except Exception:
                    pass
                return None

            lowered = joined.lower()
            if "sorry, this username is invalid." in lowered or "invalid" in lowered:
                continue

            if "already taken" in lowered or "is taken" in lowered:
                continue

            if ("Done!" in joined) or ("Congratulations" in joined) or ("You will find it at" in joined):
                token = extract_token(joined) or ""
                if not token:
                    for _ in range(12):
                        try:
                            recent = await client.get_messages(peer, limit=8)
                            for mm in recent:
                                txt = (getattr(mm, "raw_text", "") or getattr(mm, "message", "") or "")
                                t = extract_token(txt)
                                if t:
                                    token = t
                                    break
                            if token:
                                break
                        except Exception:
                            pass
                        await asyncio.sleep(0.7)
                return uname, token

        return None

    async def _set_userpic(self, client: TelegramClient, username: str):
        if not self.image_path or not Path(self.image_path).exists():
            self.log.emit("[WARN] Картинка не выбрана — пропуск аватарки.")
            return
        peer = self.chat

        last = await client.get_messages(peer, limit=1)
        last_id = last[0].id if last else 0
        await client(SendMessageRequest(peer, "/setuserpic"))
        choose_prompt = await self._wait_for_message_contains(
            client,
            peer,
            last_id,
            ["Choose a bot to change profile photo", "Choose a bot to change profile photo."],
            timeout=20.0
        )
        if not choose_prompt:
            self.log.emit("[WARN] Нет запроса выбора бота для аватарки.")
            return

        last = await client.get_messages(peer, limit=1)
        last_id = last[0].id if last else 0
        await client(SendMessageRequest(peer, f"@{username}"))
        ok_prompt = await self._wait_for_new_message(client, peer, last_id, timeout=20.0)
        if not ok_prompt:
            self.log.emit("[WARN] Нет подтверждения выбора бота для аватарки.")
            return
        if "Invalid bot selected" in ok_prompt:
            self.log.emit("[WARN] Invalid bot selected — повторяем выбор.")
            last = await client.get_messages(peer, limit=1)
            last_id = last[0].id if last else 0
            await client(SendMessageRequest(peer, f"@{username}"))
            ok_prompt = await self._wait_for_message_contains(
                client,
                peer,
                last_id,
                ["OK. Send me the new profile photo", "Send me the new profile photo"],
                timeout=20.0
            )
            if not ok_prompt:
                return
        if "OK. Send me the new profile photo" not in ok_prompt:
            ok_prompt = await self._wait_for_message_contains(
                client,
                peer,
                last_id,
                ["OK. Send me the new profile photo", "Send me the new profile photo"],
                timeout=20.0
            )
            if not ok_prompt:
                self.log.emit("[WARN] Нет запроса на отправку фото.")
                return

        await client.send_file(peer, self.image_path)
        last = await client.get_messages(peer, limit=1)
        last_id = last[0].id if last else 0
        done = await self._wait_for_message_contains(
            client,
            peer,
            last_id,
            ["Success! Profile photo updated", "/help"],
            timeout=25.0
        )
        if not done:
            self.log.emit("[WARN] Нет подтверждения установки аватарки. (Возможно не успела загрузиться, проверьте вручную)")

    def _write_token(self, username: str, token: str, hamster: str, account: str):
        ensure_file(self.cfg.tokens_txt_path())
        ensure_file(self.cfg.tokens_csv_path())
        with open(self.cfg.tokens_txt_path(), "a", encoding="utf-8") as f:
            f.write(f"{token}\n")
        exists = self.cfg.tokens_csv_path().exists() and self.cfg.tokens_csv_path().stat().st_size > 0
        with open(self.cfg.tokens_csv_path(), "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if not exists:
                w.writerow(["username", "token", "hamster", "account", "ts"])
            w.writerow([username, token, hamster, account, int(time.time())])

    def _write_revoked_token(self, username: str, token: str, account: str):
        ensure_file(self.cfg.revoked_tokens_txt_path())
        with open(self.cfg.revoked_tokens_txt_path(), "a", encoding="utf-8") as f:
            f.write(f"{username},{account},{token}\n")

    async def _delete_bot(self, client: TelegramClient, username: str) -> bool:
        peer = self.chat
        last = await client.get_messages(peer, limit=1)
        last_id = last[0].id if last else 0
        await client(SendMessageRequest(peer, "/start"))
        await asyncio.sleep(0.5)
        await self._wait_for_new_message(client, peer, last_id, timeout=12.0)

        last = await client.get_messages(peer, limit=1)
        last_id = last[0].id if last else 0
        await client(SendMessageRequest(peer, "/deletebot"))
        choose = await self._wait_for_message_contains(
            client,
            peer,
            last_id,
            ["Choose a bot to delete"],
            timeout=20.0
        )
        if not choose:
            self.log.emit("[WARN] Нет запроса выбора бота для удаления.")
            return False

        last = await client.get_messages(peer, limit=1)
        last_id = last[0].id if last else 0
        await client(SendMessageRequest(peer, f"@{username}"))
        await self._wait_for_new_message(client, peer, last_id, timeout=12.0)

        last = await client.get_messages(peer, limit=1)
        last_id = last[0].id if last else 0
        await client(SendMessageRequest(peer, "Yes, I am totally sure."))
        done = await self._wait_for_message_contains(
            client,
            peer,
            last_id,
            ["Done! The bot is gone", "/help"],
            timeout=20.0
        )
        return bool(done)

    async def _revoke_token(self, client: TelegramClient, username: str, account: str) -> Optional[str]:
        peer = self.chat
        last = await client.get_messages(peer, limit=1)
        last_id = last[0].id if last else 0
        await client(SendMessageRequest(peer, "/start"))
        await asyncio.sleep(0.5)
        await self._wait_for_new_message(client, peer, last_id, timeout=12.0)

        last = await client.get_messages(peer, limit=1)
        last_id = last[0].id if last else 0
        await client(SendMessageRequest(peer, "/revoke"))
        choose = await self._wait_for_message_contains(
            client,
            peer,
            last_id,
            ["Choose a bot to generate a new token", "Warning: your old token will stop working"],
            timeout=20.0
        )
        if not choose:
            self.log.emit("[WARN] Нет запроса выбора бота для revoke.")
            return None

        last = await client.get_messages(peer, limit=1)
        last_id = last[0].id if last else 0
        await client(SendMessageRequest(peer, f"@{username}"))
        done = await self._wait_for_message_contains(
            client,
            peer,
            last_id,
            ["Your token was replaced with a new one", "new token"],
            timeout=20.0
        )
        if not done:
            self.log.emit("[WARN] Нет подтверждения revoke токена.")
            return None
        token = extract_token(done) or ""
        if token:
            self._write_revoked_token(username, token, account)
        return token or None

    async def _run_async(self):
        if self.mode == "delete":
            await self._run_delete()
            return
        if self.mode == "revoke":
            await self._run_revoke()
            return
        accs = parse_accounts(ACCOUNTS_FILE)
        if not accs:
            self.log.emit("[ERROR] accounts_tg.txt не найден или пуст.")
            return

        names_queue = list(self.names)
        frozen = load_json(FROZEN_FILE, {})
        per_acc = {a["phone"]: 0 for a in accs}
        round_attempts = 0
        round_created = 0
        rounds_without_success = 0

        def is_frozen(phone: str) -> bool:
            until = safe_int(str(frozen.get(phone, 0)), 0)
            return until > int(time.time())

        self.log.emit(f"[INFO] Аккаунтов: {len(accs)} | Имен: {len(names_queue)} | Лимит/акк: {self.cfg.per_account_limit} (1 запуск = 1 круг)")

        acc_index = 0
        while names_queue and not self.stop_requested:
            acc = accs[acc_index % len(accs)]
            acc_index += 1
            round_attempts += 1

            self.current_phone = acc["phone"]
            if per_acc[acc["phone"]] >= self.cfg.per_account_limit:
                if round_attempts >= len(accs):
                    if round_created == 0:
                        rounds_without_success += 1
                    else:
                        rounds_without_success = 0
                    round_attempts = 0
                    round_created = 0
                if rounds_without_success >= 3:
                    self.no_available_accounts = True
                    self.remaining_names = list(names_queue)
                    self.log.emit("[ERROR] Нет доступных аккаунтов для создания.")
                    break
                continue
            if is_frozen(acc["phone"]):
                if round_attempts >= len(accs):
                    if round_created == 0:
                        rounds_without_success += 1
                    else:
                        rounds_without_success = 0
                    round_attempts = 0
                    round_created = 0
                if rounds_without_success >= 3:
                    self.no_available_accounts = True
                    self.remaining_names = list(names_queue)
                    self.log.emit("[ERROR] Нет доступных аккаунтов для создания.")
                    break
                continue
            if self.account_status.get(acc["phone"], {}).get("state") == "too_many":
                if round_attempts >= len(accs):
                    if round_created == 0:
                        rounds_without_success += 1
                    else:
                        rounds_without_success = 0
                    round_attempts = 0
                    round_created = 0
                if rounds_without_success >= 3:
                    self.no_available_accounts = True
                    self.remaining_names = list(names_queue)
                    self.log.emit("[ERROR] Нет доступных аккаунтов для создания.")
                    break
                continue

            base = names_queue.pop(0)
            self.progress.emit(f"Создание: {base} | Акк: {acc['phone']} ({per_acc[acc['phone']]}/{self.cfg.per_account_limit})")

            session_path = SESSIONS_DIR / acc["phone"]
            client = TelegramClient(str(session_path), acc["api_id"], acc["api_hash"])

            try:
                await client.connect()
                await self._ensure_auth(client, acc)

                created = await self._create_one_bot(client, base)
                if created is None:
                    # requeue and freeze if needed
                    names_queue.insert(0, base)
                    msgs = await client.get_messages(self.chat, limit=1)
                    txt = msgs[0].text if msgs else ""
                    sec = extract_try_again_seconds(txt)
                    if sec and sec > self.cfg.freeze_threshold_seconds:
                        frozen[acc["phone"]] = int(time.time()) + sec + 2
                        save_json(FROZEN_FILE, frozen)
                        self.log.emit(f"[FREEZE] {acc['phone']} заморожен на {sec}s. Переходим к следующему аккаунту, начинаю создание заново.")
                    else:
                        self.log.emit("[WARN] Не удалось создать бота — пробуем другим аккаунтом.")
                    if round_attempts >= len(accs):
                        if round_created == 0:
                            rounds_without_success += 1
                        else:
                            rounds_without_success = 0
                        round_attempts = 0
                        round_created = 0
                    if rounds_without_success >= 3:
                        self.no_available_accounts = True
                        self.remaining_names = list(names_queue)
                        self.log.emit("[ERROR] Нет доступных аккаунтов для создания.")
                        break
                    continue

                username, token = created
                self.log.emit(f"[OK] Создан @{username}")
                round_created += 1
                if token:
                    self._write_token(username, token, self.hamster, acc["phone"])
                    self.log.emit("[OK] Токен сохранён.")
                else:
                    self.log.emit("[WARN] Токен не найден (Проверьте вручную).")

                await self._set_userpic(client, username)
                per_acc[acc["phone"]] += 1
                if round_attempts >= len(accs):
                    if round_created == 0:
                        rounds_without_success += 1
                    else:
                        rounds_without_success = 0
                    round_attempts = 0
                    round_created = 0
                if rounds_without_success >= 3:
                    self.no_available_accounts = True
                    self.remaining_names = list(names_queue)
                    self.log.emit("[ERROR] Нет доступных аккаунтов для создания.")
                    break

            except FloodWaitError as e:
                sec = int(getattr(e, "seconds", 0) or 0)
                names_queue.insert(0, base)
                if sec > self.cfg.freeze_threshold_seconds:
                    frozen[acc["phone"]] = int(time.time()) + sec + 2
                    save_json(FROZEN_FILE, frozen)
                    self.log.emit(f"[FREEZE] FloodWait {sec}s. Акк заморожен, бот НЕ потерян.")
                else:
                    self.log.emit(f"[RATE] FloodWait {sec}s. Ждём.")
                    await self._wait_rate(sec + 1)
                if round_attempts >= len(accs):
                    if round_created == 0:
                        rounds_without_success += 1
                    else:
                        rounds_without_success = 0
                    round_attempts = 0
                    round_created = 0
                if rounds_without_success >= 3:
                    self.no_available_accounts = True
                    self.remaining_names = list(names_queue)
                    self.log.emit("[ERROR] Нет доступных аккаунтов для создания.")
                    break
            except Exception as e:
                names_queue.insert(0, base)
                self.log.emit(f"[ERROR] {e}")
                if round_attempts >= len(accs):
                    if round_created == 0:
                        rounds_without_success += 1
                    else:
                        rounds_without_success = 0
                    round_attempts = 0
                    round_created = 0
                if rounds_without_success >= 3:
                    self.no_available_accounts = True
                    self.remaining_names = list(names_queue)
                    self.log.emit("[ERROR] Нет доступных аккаунтов для создания.")
                    break
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass

        self.log.emit("[OK] Готово.")

    async def _run_delete(self):
        accs = parse_accounts(ACCOUNTS_FILE)
        if not accs:
            self.log.emit("[ERROR] accounts_tg.txt не найден или пуст.")
            return
        if not self.delete_targets:
            self.log.emit("[ERROR] Нет выбранных ботов для удаления.")
            return
        acc_by_phone = {a["phone"]: a for a in accs}
        for target in self.delete_targets:
            if self.stop_requested:
                break
            username = (target.get("username") or "").strip()
            phone = (target.get("account") or "").strip()
            if not username or not phone:
                self.log.emit("[WARN] Пропуск: нет username или аккаунта.")
                continue
            acc = acc_by_phone.get(phone)
            if not acc:
                self.log.emit(f"[WARN] Аккаунт {phone} не найден в accounts_tg.txt.")
                continue
            self.current_phone = acc["phone"]
            session_path = SESSIONS_DIR / acc["phone"]
            client = TelegramClient(str(session_path), acc["api_id"], acc["api_hash"])
            try:
                await client.connect()
                await self._ensure_auth(client, acc)
                ok = await self._delete_bot(client, username)
                if ok:
                    self.log.emit(f"[OK] Удалён @{username}")
                else:
                    self.log.emit(f"[ERROR] Не удалось удалить @{username}")
            except Exception as e:
                self.log.emit(f"[ERROR] {e}")
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass
        self.log.emit("[OK] Удаление завершено.")

    async def _run_revoke(self):
        accs = parse_accounts(ACCOUNTS_FILE)
        if not accs:
            self.log.emit("[ERROR] accounts_tg.txt не найден или пуст.")
            return
        if not self.revoke_targets:
            self.log.emit("[ERROR] Нет выбранного бота для revoke.")
            return
        acc_by_phone = {a["phone"]: a for a in accs}
        for target in self.revoke_targets:
            if self.stop_requested:
                break
            username = (target.get("username") or "").strip()
            phone = (target.get("account") or "").strip()
            if not username or not phone:
                self.log.emit("[WARN] Пропуск: нет username или аккаунта.")
                continue
            acc = acc_by_phone.get(phone)
            if not acc:
                self.log.emit(f"[WARN] Аккаунт {phone} не найден в accounts_tg.txt.")
                continue
            self.current_phone = acc["phone"]
            session_path = SESSIONS_DIR / acc["phone"]
            client = TelegramClient(str(session_path), acc["api_id"], acc["api_hash"])
            try:
                await client.connect()
                await self._ensure_auth(client, acc)
                token = await self._revoke_token(client, username, acc["phone"])
                if token:
                    self.revoked_results.append((username, token))
                    self.log.emit(f"[OK] Revoke токен для @{username} сохранён.")
                else:
                    self.log.emit(f"[ERROR] Не удалось выполнить revoke для @{username}")
            except Exception as e:
                self.log.emit(f"[ERROR] {e}")
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass
        self.log.emit("[OK] Revoke завершён.")

class AutoPage(QWidget):
    def __init__(self, ui):
        super().__init__()
        self.ui = ui
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0)

        card = QFrame(); card.setObjectName("Card")
        apply_shadow(card, blur=28, alpha=150, offset=QPointF(0, 8))
        c = QVBoxLayout(card); c.setContentsMargins(18,18,18,18); c.setSpacing(12)

        self.title = QLabel("Автоматическое создание"); self.title.setObjectName("PageTitle")
        c.addWidget(self.title)

        self.chat = QLineEdit(BOTFATHER_USERNAME_DEFAULT); self.chat.setObjectName("Input")
        self.names = QLineEdit(""); self.names.setObjectName("Input")
        self.names.setPlaceholderText("name/name2/name3 (без пробелов)")

        self.hamster = QComboBox(); self.hamster.setObjectName("Input")
        hamster_view = QListView()
        hamster_view.setUniformItemSizes(True)
        self.hamster.setView(hamster_view)
        self.hamster.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.hamster.setMinimumContentsLength(12)
        self.hamster.addItem("None")

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(6)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        self.lbl_chat = QLabel("Чат:")
        self.lbl_names = QLabel("Имена:")
        self.lbl_hamster = QLabel("Хомяк:")
        form.addRow(self.lbl_chat, self.chat)
        form.addRow(self.lbl_names, self.names)
        form.addRow(self.lbl_hamster, self.hamster)

        row = QHBoxLayout()
        self.pick_img = QPushButton("Выбрать аватарку (обязательно)"); self.pick_img.setObjectName("PrimaryBtn")
        self.pick_img.clicked.connect(self.ui.pick_image)
        self.open_tokens = QPushButton("Открыть tokens.txt"); self.open_tokens.setObjectName("SecondaryBtn")
        self.open_tokens.clicked.connect(self.ui.open_tokens_txt)
        row.addWidget(self.pick_img)
        row.addWidget(self.open_tokens)
        row.addStretch(1)

        limit_row = QHBoxLayout()
        self.limit_hint = QLabel(""); self.limit_hint.setObjectName("Hint")
        self.limit_edit = QPushButton("Изменить лимит"); self.limit_edit.setObjectName("SecondaryBtn")
        self.limit_edit.clicked.connect(self.change_limit)
        limit_row.addWidget(self.limit_hint)
        limit_row.addStretch(1)
        limit_row.addWidget(self.limit_edit)

        btn_row = QHBoxLayout()
        self.custom = QPushButton("Кастомизация"); self.custom.setObjectName("SecondaryBtn")
        self.edit = QPushButton("Изменить"); self.edit.setObjectName("SecondaryBtn")
        self.start = QPushButton("Запуск (Авто режим)"); self.start.setObjectName("PrimaryBtn")
        self.stop = QPushButton("Стоп"); self.stop.setObjectName("SecondaryBtn")

        self.custom.clicked.connect(self.ui.open_customization)
        self.edit.clicked.connect(self.ui.open_bot_customization)
        self.start.clicked.connect(self.ui.start_auto)
        self.stop.clicked.connect(self.ui.stop_worker)

        btn_row.addWidget(self.custom); btn_row.addWidget(self.edit); btn_row.addWidget(self.start); btn_row.addWidget(self.stop); btn_row.addStretch(1)

        c.addLayout(form)
        c.addLayout(row)
        self.update_limit_hint()
        c.addLayout(limit_row)
        c.addLayout(btn_row)

        lay.addWidget(card)
        lay.addWidget(self.ui.logbox, 1)

    def update_limit_hint(self):
        self.limit_hint.setText(self.ui.format_limit_hint(self.ui.cfg.per_account_limit))

    def update_language(self, t: Dict[str, str]):
        self.title.setText(t["auto_title"])
        self.lbl_chat.setText(t["auto_chat"])
        self.lbl_names.setText(t["auto_names"])
        self.lbl_hamster.setText(t["auto_hamster"])
        self.names.setPlaceholderText(t["auto_names_placeholder"])
        self.pick_img.setText(t["auto_pick_img"])
        self.open_tokens.setText(t["auto_open_tokens"])
        self.limit_edit.setText(t["auto_limit_edit"])
        self.custom.setText(t["auto_custom"])
        self.edit.setText(t["auto_edit"])
        self.start.setText(t["auto_start"])
        self.stop.setText(t["auto_stop"])

    def change_limit(self):
        dlg = StyledDialog(self, "Лимит ботов")
        dlg.resize(520, 260)

        label = QLabel("Сколько ботов можно создать на аккаунт за запуск?")
        label.setWordWrap(True)
        label.setObjectName("Hint")

        spin = QSpinBox()
        spin.setRange(1, 50)
        spin.setValue(int(self.ui.cfg.per_account_limit))
        spin.setObjectName("Input")

        row = QHBoxLayout()
        ok = QPushButton("ОК"); ok.setObjectName("PrimaryBtn")
        cancel = QPushButton("Отмена"); cancel.setObjectName("SecondaryBtn")
        row.addWidget(ok); row.addWidget(cancel); row.addStretch(1)

        body = QVBoxLayout()
        body.addWidget(label)
        body.addWidget(spin)
        body.addLayout(row)
        dlg.set_body_layout(body)

        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.ui.cfg.per_account_limit = int(spin.value())
            self.ui.save_config()
            self.update_limit_hint()

class BotsPage(QWidget):
    def __init__(self, ui):
        super().__init__()
        self.ui = ui
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0)

        card = QFrame(); card.setObjectName("Card")
        apply_shadow(card, blur=28, alpha=150, offset=QPointF(0, 8))
        c = QVBoxLayout(card); c.setContentsMargins(18,18,18,18); c.setSpacing(12)

        self.title = QLabel("Боты"); self.title.setObjectName("PageTitle")
        self.hint = QLabel("Список ботов и аккаунтов, на которых они созданы."); self.hint.setObjectName("Hint")
        c.addWidget(self.title)
        c.addWidget(self.hint)

        self.table = QTableWidget(0, 3)
        self.table.setObjectName("StatsTable")
        configure_table(self.table)

        try:
            self.table.setCornerButtonEnabled(False)
        except Exception:
            pass
        try:
            self.table.verticalHeader().setStyleSheet("QHeaderView::section{background: rgba(18,26,46,0.85); color: rgba(230,237,243,0.90); border: none;}")
            self.table.horizontalHeader().setStyleSheet("QHeaderView::section{background: rgba(18,26,46,0.85); color: rgba(230,237,243,0.90); border: none;}")
            self.table.setStyleSheet(self.table.styleSheet() + " QTableCornerButton::section{background: rgba(18,26,46,0.85); border:none;} QHeaderView{background: transparent;} ")
            from PyQt6.QtGui import QColor
            pal = self.table.palette()
            pal.setColor(pal.ColorRole.Base, QColor(10,16,30))
            pal.setColor(pal.ColorRole.Window, QColor(10,16,30))
            pal.setColor(pal.ColorRole.Button, QColor(18,26,46))
            pal.setColor(pal.ColorRole.Text, QColor(230,237,243))
            self.table.setPalette(pal)
            self.table.viewport().setAutoFillBackground(False)
        except Exception:
            pass
        self.table.setCornerButtonEnabled(False)

        self.table.setHorizontalHeaderLabels(["Бот", "Аккаунт", "Создан"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        c.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.refresh = QPushButton("Обновить"); self.refresh.setObjectName("PrimaryBtn")
        self.refresh.clicked.connect(self.refresh_table)
        btn_row.addWidget(self.refresh); btn_row.addStretch(1)
        c.addLayout(btn_row)

        lay.addWidget(card)
        self.refresh_table()

    def update_language(self, t: Dict[str, str]):
        self.title.setText(t["bots_title"])
        self.hint.setText(t["bots_hint"])
        self.refresh.setText(t["bots_refresh"])

    def refresh_table(self):
        rows = []
        csv_path = self.ui.cfg.tokens_csv_path()
        if csv_path.exists():
            try:
                with open(csv_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        rows.append(row)
            except Exception:
                pass

        self.table.setRowCount(0)
        for row in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            username = (row.get("username") or "").strip()
            account = (row.get("account") or row.get("phone") or "").strip()
            ts_raw = (row.get("ts") or "").strip()
            ts_text = ""
            if ts_raw.isdigit():
                try:
                    ts_text = time.strftime("%d.%m.%Y %H:%M", time.localtime(int(ts_raw)))
                except Exception:
                    ts_text = ts_raw
            self.table.setItem(r, 0, QTableWidgetItem(username))
            self.table.setItem(r, 1, QTableWidgetItem(account or "-"))
            self.table.setItem(r, 2, QTableWidgetItem(ts_text))

class ManageBotsPage(QWidget):
    def __init__(self, ui):
        super().__init__()
        self.ui = ui
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0)

        card = QFrame(); card.setObjectName("Card")
        apply_shadow(card, blur=28, alpha=150, offset=QPointF(0, 8))
        c = QVBoxLayout(card); c.setContentsMargins(18,18,18,18); c.setSpacing(12)

        self.title = QLabel("Удаление и Revoke Token"); self.title.setObjectName("PageTitle")
        self.hint = QLabel("Выберите ботов в таблице для массового удаления или revoke токена."); self.hint.setObjectName("Hint")
        c.addWidget(self.title)
        c.addWidget(self.hint)

        self.table = QTableWidget(0, 2)
        self.table.setObjectName("StatsTable")
        configure_table(self.table)
        self.table.setHorizontalHeaderLabels(["Бот", "Аккаунт"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        c.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.refresh = QPushButton("Обновить список"); self.refresh.setObjectName("SecondaryBtn")
        self.delete_mass = QPushButton("Массовое удаление"); self.delete_mass.setObjectName("PrimaryBtn")
        self.delete_single = QPushButton("Единичное удаление"); self.delete_single.setObjectName("SecondaryBtn")
        btn_row.addWidget(self.refresh)
        btn_row.addSpacing(12)
        btn_row.addWidget(self.delete_mass)
        btn_row.addWidget(self.delete_single)
        btn_row.addStretch(1)
        c.addLayout(btn_row)

        revoke_row = QHBoxLayout()
        self.revoke_mass = QPushButton("Массовый Revoke"); self.revoke_mass.setObjectName("PrimaryBtn")
        self.revoke = QPushButton("Revoke Token"); self.revoke.setObjectName("SecondaryBtn")
        self.open_revoked = QPushButton("Открыть revoke_tokens.txt"); self.open_revoked.setObjectName("SecondaryBtn")
        revoke_row.addWidget(self.revoke_mass)
        revoke_row.addWidget(self.revoke)
        revoke_row.addWidget(self.open_revoked)
        revoke_row.addStretch(1)
        c.addLayout(revoke_row)

        lay.addWidget(card)

        self.refresh.clicked.connect(self.refresh_table)
        self.delete_mass.clicked.connect(self.ui.delete_mass)
        self.delete_single.clicked.connect(self.ui.delete_single)
        self.revoke_mass.clicked.connect(self.ui.revoke_mass)
        self.revoke.clicked.connect(self.ui.revoke_token)
        self.open_revoked.clicked.connect(self.ui.open_revoked_tokens_txt)

        self.refresh_table()

    def refresh_table(self):
        rows = []
        csv_path = self.ui.cfg.tokens_csv_path()
        if csv_path.exists():
            try:
                with open(csv_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        rows.append(row)
            except Exception:
                pass

        self.table.setRowCount(0)
        for row in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            username = (row.get("username") or "").strip()
            account = (row.get("account") or row.get("phone") or "").strip()
            self.table.setItem(r, 0, QTableWidgetItem(username))
            self.table.setItem(r, 1, QTableWidgetItem(account or "-"))

    def selected_targets(self) -> List[Dict[str, str]]:
        targets = []
        rows = sorted({idx.row() for idx in self.table.selectionModel().selectedRows()})
        for r in rows:
            username_item = self.table.item(r, 0)
            account_item = self.table.item(r, 1)
            username = username_item.text().strip() if username_item else ""
            account = account_item.text().strip() if account_item else ""
            if username and account and account != "-":
                targets.append({"username": username, "account": account})
        return targets

    def update_language(self, t: Dict[str, str]):
        self.title.setText(t["manage_title"])
        self.hint.setText(t["manage_hint"])
        self.refresh.setText(t["manage_refresh"])
        self.delete_mass.setText(t["manage_delete_mass"])
        self.delete_single.setText(t["manage_delete_single"])
        self.revoke_mass.setText(t["manage_revoke_mass"])
        self.revoke.setText(t["manage_revoke_single"])
        self.open_revoked.setText(t["manage_open_revoked"])

class SettingsPage(QWidget):
    def __init__(self, ui):
        super().__init__()
        self.ui = ui
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0)

        card = QFrame(); card.setObjectName("Card")
        apply_shadow(card, blur=28, alpha=150, offset=QPointF(0, 8))
        c = QVBoxLayout(card); c.setContentsMargins(18,18,18,18); c.setSpacing(12)

        self.title = QLabel("Настройки"); self.title.setObjectName("PageTitle")
        self.hint = QLabel(""); self.hint.setObjectName("Hint")
        c.addWidget(self.title)
        c.addWidget(self.hint)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)

        self.lang_label = QLabel("Язык:")
        self.lang_combo = QComboBox(); self.lang_combo.setObjectName("Input")
        self.lang_combo.addItems(["Русский", "English"])
        form.addRow(self.lang_label, self.lang_combo)

        self.autostart_label = QLabel("Автозапуск с Windows:")
        self.autostart_toggle = QCheckBox("Включить автозапуск")
        form.addRow(self.autostart_label, self.autostart_toggle)

        c.addLayout(form)

        btn_row = QHBoxLayout()
        self.backup_btn = QPushButton("Создать резервную копию"); self.backup_btn.setObjectName("PrimaryBtn")
        self.restore_btn = QPushButton("Импорт резервной копии"); self.restore_btn.setObjectName("SecondaryBtn")
        self.reset_btn = QPushButton("Сброс до заводских настроек"); self.reset_btn.setObjectName("SecondaryBtn")
        btn_row.addWidget(self.backup_btn)
        btn_row.addWidget(self.restore_btn)
        btn_row.addWidget(self.reset_btn)
        btn_row.addStretch(1)
        c.addLayout(btn_row)

        help_row = QHBoxLayout()
        self.onboarding_btn = QPushButton("Мастер новичка"); self.onboarding_btn.setObjectName("SecondaryBtn")
        self.support_btn = QPushButton("Тех. Поддержка"); self.support_btn.setObjectName("PrimaryBtn")
        help_row.addWidget(self.onboarding_btn)
        help_row.addWidget(self.support_btn)
        help_row.addStretch(1)
        c.addLayout(help_row)

        lay.addWidget(card)

        self.lang_combo.currentTextChanged.connect(self.ui.set_language)
        self.autostart_toggle.toggled.connect(self.ui.toggle_autostart)
        self.backup_btn.clicked.connect(self.ui.create_backup)
        self.restore_btn.clicked.connect(self.ui.restore_backup)
        self.reset_btn.clicked.connect(self.ui.reset_factory)
        self.onboarding_btn.clicked.connect(self.ui.open_onboarding)
        self.support_btn.clicked.connect(self.ui.open_support)

        self.refresh_state()

    def refresh_state(self):
        lang = getattr(self.ui.cfg, "language", "Русский")
        idx = self.lang_combo.findText(lang)
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        self.autostart_toggle.setChecked(self.ui.is_autostart_enabled())

    def update_language(self, t: Dict[str, str]):
        self.title.setText(t["settings_title"])
        self.hint.setText(t["settings_hint"])
        self.lang_label.setText(t["settings_language"])
        self.autostart_label.setText(t["settings_autostart_label"])
        self.autostart_toggle.setText(t["settings_autostart_toggle"])
        self.backup_btn.setText(t["settings_backup"])
        self.restore_btn.setText(t["settings_restore"])
        self.reset_btn.setText(t["settings_reset"])
        self.onboarding_btn.setText(t["settings_onboarding"])
        self.support_btn.setText(t["settings_support"])

class TokensPage(QWidget):
    def __init__(self, ui):
        super().__init__()
        self.ui = ui
        self.current_date = None
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0)

        card = QFrame(); card.setObjectName("Card")
        apply_shadow(card, blur=28, alpha=150, offset=QPointF(0, 8))
        c = QVBoxLayout(card); c.setContentsMargins(18,18,18,18); c.setSpacing(12)

        self.title = QLabel("Токены"); self.title.setObjectName("PageTitle")
        self.hint = QLabel("Токены сгруппированы по датам. Можно копировать, редактировать и удалять."); self.hint.setObjectName("Hint")
        c.addWidget(self.title)
        c.addWidget(self.hint)

        body = QHBoxLayout()
        self.tree = QTreeWidget()
        self.tree.setObjectName("StatsTable")
        configure_table(self.tree)
        self.tree.setHeaderLabels(["Дата / Токен", "Бот"])
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setUniformRowHeights(True)
        self.tree.setIndentation(18)
        self.tree.setRootIsDecorated(True)
        self.tree.setExpandsOnDoubleClick(True)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tree.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tree.setColumnWidth(0, 260)
        self.tree.setColumnWidth(1, 180)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tree.headerItem().setTextAlignment(0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.tree.headerItem().setTextAlignment(1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        try:
            self.tree.header().setStyleSheet("QHeaderView::section{background: rgba(18,26,46,0.85); color: rgba(230,237,243,0.90); border: none;}")
            from PyQt6.QtGui import QColor
            pal = self.tree.palette()
            pal.setColor(pal.ColorRole.Base, QColor(10,16,30))
            pal.setColor(pal.ColorRole.Window, QColor(10,16,30))
            pal.setColor(pal.ColorRole.Text, QColor(230,237,243))
            self.tree.setPalette(pal)
            self.tree.viewport().setAutoFillBackground(False)
        except Exception:
            pass
        self.tree.itemSelectionChanged.connect(self._on_select)
        body.addWidget(self.tree, 2)

        right = QVBoxLayout()
        self.date_label = QLabel("Дата: —"); self.date_label.setObjectName("Hint")
        self.editor = QPlainTextEdit(); self.editor.setObjectName("Input")
        self.editor.setPlaceholderText("Токены для выбранной даты (по одному в строке)...")
        right.addWidget(self.date_label)
        right.addWidget(self.editor, 1)
        body.addLayout(right, 3)

        c.addLayout(body)

        btn_row = QVBoxLayout()
        row1 = QHBoxLayout()
        row2 = QHBoxLayout()
        self.refresh = QPushButton("Обновить"); self.refresh.setObjectName("SecondaryBtn")
        self.save = QPushButton("Сохранить изменения"); self.save.setObjectName("PrimaryBtn")
        self.copy_selected = QPushButton("Копировать выбранные"); self.copy_selected.setObjectName("SecondaryBtn")
        self.copy_latest = QPushButton("Копировать последние"); self.copy_latest.setObjectName("SecondaryBtn")
        self.delete_selected = QPushButton("Удалить выбранные"); self.delete_selected.setObjectName("SecondaryBtn")
        self.clear_all = QPushButton("Очистить список"); self.clear_all.setObjectName("SecondaryBtn")

        self.refresh.clicked.connect(self.refresh_view)
        self.save.clicked.connect(self.save_current_group)
        self.copy_selected.clicked.connect(self.copy_selected_groups)
        self.copy_latest.clicked.connect(self.copy_latest_group)
        self.delete_selected.clicked.connect(self.delete_selected_groups)
        self.clear_all.clicked.connect(self.clear_tokens)

        row1.addWidget(self.refresh)
        row1.addWidget(self.save)
        row1.addWidget(self.copy_selected)
        row1.addStretch(1)
        row2.addWidget(self.copy_latest)
        row2.addWidget(self.delete_selected)
        row2.addWidget(self.clear_all)
        row2.addStretch(1)
        btn_row.addLayout(row1)
        btn_row.addLayout(row2)
        c.addLayout(btn_row)

        lay.addWidget(card)
        self.refresh_view()

    def update_language(self, t: Dict[str, str]):
        self.title.setText(t["tokens_title"])
        self.hint.setText(t["tokens_hint"])
        self.editor.setPlaceholderText(t["tokens_placeholder"])
        self.refresh.setText(t["tokens_refresh"])
        self.save.setText(t["tokens_save"])
        self.copy_selected.setText(t["tokens_copy_selected"])
        self.copy_latest.setText(t["tokens_copy_latest"])
        self.delete_selected.setText(t["tokens_delete_selected"])
        self.clear_all.setText(t["tokens_clear"])

    def _load_rows(self) -> List[Dict]:
        rows = []
        csv_path = self.ui.cfg.tokens_csv_path()
        if csv_path.exists():
            try:
                with open(csv_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        rows.append(row)
            except Exception:
                pass
        return rows

    def _date_key(self, row: Dict) -> str:
        ts_raw = (row.get("ts") or "").strip()
        if ts_raw.isdigit():
            try:
                return time.strftime("%Y-%m-%d", time.localtime(int(ts_raw)))
            except Exception:
                return "Без даты"
        return "Без даты"

    def refresh_view(self):
        self.tree.clear()
        rows = self._load_rows()
        groups: Dict[str, List[Dict]] = {}
        for row in rows:
            key = self._date_key(row)
            groups.setdefault(key, []).append(row)

        bold_font = QFont()
        bold_font.setBold(True)
        bold_font.setPointSize(11)
        token_font = QFont()
        token_font.setBold(True)
        for date_key in sorted(groups.keys()):
            top = QTreeWidgetItem([f"{date_key} ({len(groups[date_key])})", ""])
            top.setData(0, Qt.ItemDataRole.UserRole, date_key)
            top.setFont(0, bold_font)
            top.setFont(1, bold_font)
            top.setTextAlignment(0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            top.setTextAlignment(1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            top.setFlags(top.flags() | Qt.ItemFlag.ItemIsSelectable)
            top.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            for col in range(2):
                top.setBackground(col, QBrush(QColor(10, 16, 30)))
            for row in groups[date_key]:
                token = (row.get("token") or "").strip()
                username = (row.get("username") or "").strip()
                child = QTreeWidgetItem([token, username])
                child.setFont(0, token_font)
                child.setFont(1, token_font)
                child.setTextAlignment(0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                child.setTextAlignment(1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                child.setFlags(child.flags() | Qt.ItemFlag.ItemIsSelectable)
                idx = top.childCount()
                bg = QColor(12, 18, 34) if idx % 2 == 0 else QColor(14, 20, 36)
                for col in range(2):
                    child.setBackground(col, QBrush(bg))
                top.addChild(child)
            self.tree.addTopLevelItem(top)
            top.setExpanded(False)

        self.editor.clear()
        self.current_date = None
        self.date_label.setText("Дата: —")

    def _on_select(self):
        items = self.tree.selectedItems()
        if not items:
            return
        item = items[0]
        if item.parent() is not None:
            item = item.parent()
        date_key = item.data(0, Qt.ItemDataRole.UserRole)
        if not date_key:
            return
        self.current_date = date_key
        self.date_label.setText(f"Дата: {date_key}")
        tokens = []
        for i in range(item.childCount()):
            token = item.child(i).text(0).strip()
            if token:
                tokens.append(token)
        self.editor.setPlainText("\n".join(tokens))

    def _selected_group_keys(self) -> List[str]:
        keys = []
        for item in self.tree.selectedItems():
            if item.parent() is not None:
                item = item.parent()
            key = item.data(0, Qt.ItemDataRole.UserRole)
            if key and key not in keys:
                keys.append(key)
        return keys

    def save_current_group(self):
        if not self.current_date:
            show_message(self, "Нет даты", "Выберите дату в списке слева.")
            return
        rows = self._load_rows()
        keep_rows = [r for r in rows if self._date_key(r) != self.current_date]
        tokens = [t.strip() for t in self.editor.toPlainText().splitlines() if t.strip()]
        try:
            base_ts = int(time.mktime(time.strptime(self.current_date, "%Y-%m-%d")))
        except Exception:
            base_ts = int(time.time())
        for token in tokens:
            keep_rows.append({
                "username": "",
                "token": token,
                "hamster": "",
                "account": "",
                "ts": str(base_ts),
            })
        self._write_rows(keep_rows)
        self.refresh_view()

    def copy_selected_groups(self):
        keys = self._selected_group_keys()
        if not keys:
            show_message(self, "Нет выбора", "Отметьте даты галочками слева.")
            return
        rows = self._load_rows()
        tokens = [r.get("token", "") for r in rows if self._date_key(r) in keys and r.get("token")]
        QApplication.clipboard().setText("\n".join(tokens))

    def copy_latest_group(self):
        rows = self._load_rows()
        if not rows:
            show_message(self, "Пусто", "Токены не найдены.")
            return
        latest = max((safe_int(r.get("ts", "0")), r) for r in rows)[0]
        if latest <= 0:
            show_message(self, "Пусто", "Нет дат для токенов.")
            return
        latest_date = time.strftime("%Y-%m-%d", time.localtime(latest))
        tokens = [r.get("token", "") for r in rows if self._date_key(r) == latest_date and r.get("token")]
        QApplication.clipboard().setText("\n".join(tokens))

    def delete_selected_groups(self):
        keys = self._selected_group_keys()
        if not keys:
            show_message(self, "Нет выбора", "Отметьте даты галочками слева.")
            return
        items = self.tree.selectedItems()
        target = items[0] if items else None
        if target and target.parent() is not None:
            target = target.parent()
        rect = self.tree.visualItemRect(target) if target else QRect()
        rows = self._load_rows()
        keep_rows = [r for r in rows if self._date_key(r) not in keys]
        def _finish():
            self._write_rows(keep_rows)
            self.refresh_view()
        animate_evaporate_rect(self.tree.viewport(), rect, _finish)

    def clear_tokens(self):
        rect = self.tree.viewport().rect()
        def _finish():
            self._write_rows([])
            self.refresh_view()
        animate_evaporate_rect(self.tree.viewport(), rect, _finish)

    def _write_rows(self, rows: List[Dict]):
        ensure_file(self.ui.cfg.tokens_txt_path())
        ensure_file(self.ui.cfg.tokens_csv_path())
        with open(self.ui.cfg.tokens_csv_path(), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["username", "token", "hamster", "account", "ts"])
            for row in rows:
                w.writerow([
                    row.get("username", ""),
                    row.get("token", ""),
                    row.get("hamster", ""),
                    row.get("account", ""),
                    row.get("ts", ""),
                ])
        with open(self.ui.cfg.tokens_txt_path(), "w", encoding="utf-8") as f:
            for row in rows:
                token = (row.get("token") or "").strip()
                if token:
                    f.write(f"{token}\n")

class AccountsAuthWorker(QThread):
    log = pyqtSignal(str)
    finished_ok = pyqtSignal()
    status_update = pyqtSignal(str, dict)

    def __init__(self, accounts: List[Dict], bridge: PromptBridge, only_errors: bool = False):
        super().__init__()
        self.accounts = accounts
        self.bridge = bridge
        self.only_errors = only_errors
        self.stop_requested = False

    def stop(self):
        self.stop_requested = True

    def run(self):
        asyncio.run(self._run_async())
        self.finished_ok.emit()

    async def _run_async(self):
        for acc in self.accounts:
            if self.stop_requested:
                return
            phone = acc["phone"]
            self.log.emit(f"[AUTH] {phone}")
            session_path = SESSIONS_DIR / phone
            client = TelegramClient(str(session_path), acc["api_id"], acc["api_hash"])
            try:
                await client.connect()
                if not await client.is_user_authorized():
                    await client.send_code_request(phone)
                    code = await self.bridge.get_code(phone)
                    try:
                        await client.sign_in(phone, code)
                    except SessionPasswordNeededError:
                        pwd = acc.get("password") or await self.bridge.get_password(phone)
                        if pwd:
                            await client.sign_in(password=pwd)
                    if not await client.is_user_authorized() and acc.get("password"):
                        try:
                            await client.sign_in(password=acc["password"])
                        except SessionPasswordNeededError:
                            pwd = await self.bridge.get_password(phone)
                            if pwd:
                                await client.sign_in(password=pwd)
                await client(SendMessageRequest(BOTFATHER_USERNAME_DEFAULT, "/start"))
                await asyncio.sleep(0.8)
                msgs = await client.get_messages(BOTFATHER_USERNAME_DEFAULT, limit=1)
                if msgs and (msgs[0].text or ""):
                    self.status_update.emit(phone, {"state": "ok"})
                else:
                    self.status_update.emit(phone, {"state": "error", "reason": "no_response"})
            except Exception as e:
                self.status_update.emit(phone, {"state": "error", "reason": str(e)})
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass

class AccountsPage(QWidget):
    def __init__(self, ui):
        super().__init__()
        self.ui = ui
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0)

        card = QFrame(); card.setObjectName("Card")
        apply_shadow(card, blur=28, alpha=150, offset=QPointF(0, 8))
        c = QVBoxLayout(card); c.setContentsMargins(18,18,18,18); c.setSpacing(12)

        self.title = QLabel("Аккаунты"); self.title.setObjectName("PageTitle")
        self.hint = QLabel(""); self.hint.setObjectName("Hint")
        c.addWidget(self.title)
        c.addWidget(self.hint)

        self.table = QTableWidget(0, 3)
        self.table.setObjectName("StatsTable")
        configure_table(self.table)
        self.table.setHorizontalHeaderLabels(["Телефон", "Статус", "Причина"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        try:
            self.table.setCornerButtonEnabled(False)
        except Exception:
            pass
        try:
            self.table.verticalHeader().setStyleSheet("QHeaderView::section{background: rgba(18,26,46,0.85); color: rgba(230,237,243,0.90); border: none;}")
            self.table.horizontalHeader().setStyleSheet("QHeaderView::section{background: rgba(18,26,46,0.85); color: rgba(230,237,243,0.90); border: none;}")
            self.table.setStyleSheet(self.table.styleSheet() + " QTableCornerButton::section{background: rgba(18,26,46,0.85); border:none;} QHeaderView{background: transparent;} ")
            pal = self.table.palette()
            pal.setColor(pal.ColorRole.Base, QColor(10,16,30))
            pal.setColor(pal.ColorRole.Window, QColor(10,16,30))
            pal.setColor(pal.ColorRole.Button, QColor(18,26,46))
            pal.setColor(pal.ColorRole.Text, QColor(230,237,243))
            self.table.setPalette(pal)
            self.table.viewport().setAutoFillBackground(False)
        except Exception:
            pass
        self.table.setCornerButtonEnabled(False)
        c.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("Добавить аккаунты"); self.add_btn.setObjectName("SecondaryBtn")
        self.delete_btn = QPushButton("Удалить аккаунт"); self.delete_btn.setObjectName("SecondaryBtn")
        self.auth_all = QPushButton("Авторизовать все"); self.auth_all.setObjectName("PrimaryBtn")
        self.auth_failed = QPushButton("Авторизовать ошибки"); self.auth_failed.setObjectName("SecondaryBtn")
        self.refresh = QPushButton("Обновить"); self.refresh.setObjectName("SecondaryBtn")
        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.delete_btn)
        btn_row.addWidget(self.auth_all)
        btn_row.addWidget(self.auth_failed)
        btn_row.addWidget(self.refresh)
        btn_row.addStretch(1)
        c.addLayout(btn_row)

        self.add_btn.clicked.connect(self.add_accounts)
        self.delete_btn.clicked.connect(self.delete_account)
        self.auth_all.clicked.connect(lambda: self.authorize_accounts(False))
        self.auth_failed.clicked.connect(lambda: self.authorize_accounts(True))
        self.refresh.clicked.connect(self.refresh_table)

        lay.addWidget(card)
        self.refresh_table()

    def update_language(self, t: Dict[str, str]):
        self.title.setText(t["accounts_title"])
        self.hint.setText(t["accounts_hint"])
        self.add_btn.setText(t["accounts_add"])
        self.delete_btn.setText(t["accounts_delete"])
        self.auth_all.setText(t["accounts_auth_all"])
        self.auth_failed.setText(t["accounts_auth_failed"])
        self.refresh.setText(t["accounts_refresh"])

    def refresh_table(self):
        accounts = parse_accounts(ACCOUNTS_FILE)
        self.table.setRowCount(0)
        for acc in accounts:
            phone = acc["phone"]
            status = self.ui.account_status.get(phone, {})
            state = status.get("state", "unknown")
            reason = status.get("reason", "")
            r = self.table.rowCount()
            self.table.insertRow(r)
            phone_item = QTableWidgetItem(phone)
            state_item = QTableWidgetItem(state)
            reason_item = QTableWidgetItem(reason)
            phone_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            state_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            reason_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            if state == "too_many":
                state_item.setForeground(QColor(255, 90, 90))
                phone_item.setForeground(QColor(255, 90, 90))
            self.table.setItem(r, 0, phone_item)
            self.table.setItem(r, 1, state_item)
            self.table.setItem(r, 2, reason_item)

    def add_accounts(self):
        text = show_multiline_dialog(self, "Добавить аккаунты", "Вставьте аккаунты (по одному в строке).", "phone:password:api_id:api_hash")
        if not text:
            return
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            return
        ensure_file(ACCOUNTS_FILE)
        existing = ACCOUNTS_FILE.read_text(encoding="utf-8").splitlines()
        with open(ACCOUNTS_FILE, "a", encoding="utf-8") as f:
            for line in lines:
                if line in existing:
                    continue
                f.write(f"{line}\n")
        self.refresh_table()

    def delete_account(self):
        r = self.table.currentRow()
        if r < 0:
            return
        phone = self.table.item(r, 0).text()
        rect = self.table.visualItemRect(self.table.item(r, 0))
        def _finish():
            lines = ACCOUNTS_FILE.read_text(encoding="utf-8").splitlines() if ACCOUNTS_FILE.exists() else []
            with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
                for line in lines:
                    if not line.startswith(f"{phone}:"):
                        f.write(f"{line}\n")
            session_path = SESSIONS_DIR / phone
            for ext in [".session", ".session-journal"]:
                p = session_path.with_suffix(ext)
                if p.exists():
                    try:
                        p.unlink()
                    except Exception:
                        pass
            self.ui.account_status.pop(phone, None)
            self.ui.save_account_status()
            self.refresh_table()
        animate_evaporate_rect(self.table.viewport(), rect, _finish)

    def authorize_accounts(self, only_errors: bool):
        accounts = parse_accounts(ACCOUNTS_FILE)
        if only_errors:
            accounts = [a for a in accounts if self.ui.account_status.get(a["phone"], {}).get("state") == "error"]
        if not accounts:
            show_message(self, "Нет аккаунтов", "Нет аккаунтов для авторизации.")
            return
        self.worker = AccountsAuthWorker(accounts, self.ui.bridge, only_errors=only_errors)
        self.worker.log.connect(self.ui.log)
        self.worker.status_update.connect(self._update_status)
        self.worker.start()

    def _update_status(self, phone: str, status: dict):
        self.ui.account_status[phone] = status
        self.ui.save_account_status()
        self.refresh_table()

class StatsPage(QWidget):
    def __init__(self, ui):
        super().__init__()
        self.ui = ui
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0)

        card = QFrame(); card.setObjectName("Card")
        apply_shadow(card, blur=28, alpha=150, offset=QPointF(0, 8))
        c = QVBoxLayout(card); c.setContentsMargins(18,18,18,18); c.setSpacing(12)

        self.title = QLabel("Статистика"); self.title.setObjectName("PageTitle")
        c.addWidget(self.title)

        row = QHBoxLayout()
        self.name = QLineEdit(""); self.name.setObjectName("Input"); self.name.setPlaceholderText("Название хомяка")
        self.percent = QSpinBox(); self.percent.setRange(0,100); self.percent.setValue(50); self.percent.setObjectName("Input")
        self.add_btn = QPushButton("Добавить хомяка"); self.add_btn.setObjectName("PrimaryBtn")
        self.add_btn.clicked.connect(self.add_hamster)
        row.addWidget(self.name, 2)
        self.percent_label = QLabel("Процент:")
        row.addWidget(self.percent_label)
        row.addWidget(self.percent)
        row.addWidget(self.add_btn)
        c.addLayout(row)

        self.table = QTableWidget(0, 3)
        self.table.setObjectName("StatsTable")
        configure_table(self.table)

        # Force-remove any white corner/headers forever (Windows palette override)
        try:
            self.table.setCornerButtonEnabled(False)
        except Exception:
            pass
        try:
            self.table.verticalHeader().setStyleSheet("QHeaderView::section{background: rgba(18,26,46,0.85); color: rgba(230,237,243,0.90); border: none;}")
            self.table.horizontalHeader().setStyleSheet("QHeaderView::section{background: rgba(18,26,46,0.85); color: rgba(230,237,243,0.90); border: none;}")
            self.table.setStyleSheet(self.table.styleSheet() + " QTableCornerButton::section{background: rgba(18,26,46,0.85); border:none;} QHeaderView{background: transparent;} ")
            # Palette hard override (kills rare white flash)
            from PyQt6.QtGui import QColor
            pal = self.table.palette()
            pal.setColor(pal.ColorRole.Base, QColor(10,16,30))
            pal.setColor(pal.ColorRole.Window, QColor(10,16,30))
            pal.setColor(pal.ColorRole.Button, QColor(18,26,46))
            pal.setColor(pal.ColorRole.Text, QColor(230,237,243))
            self.table.setPalette(pal)
            self.table.viewport().setAutoFillBackground(False)
        except Exception:
            pass
        self.table.setCornerButtonEnabled(False)

        try:
            self.table.horizontalHeader().setStyleSheet("background: rgba(18,26,46,0.85); color: rgba(230,237,243,0.90); border: none;")
            self.table.verticalHeader().setStyleSheet("background: rgba(18,26,46,0.85); color: rgba(230,237,243,0.90); border: none;")
        except Exception:
            pass
        self.table.setHorizontalHeaderLabels(["Хомяк", "Процент", "Ботов"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        c.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.edit = QPushButton("Редактировать"); self.edit.setObjectName("SecondaryBtn")
        self.delete = QPushButton("Удалить выбранный"); self.delete.setObjectName("SecondaryBtn")
        self.refresh = QPushButton("Обновить"); self.refresh.setObjectName("PrimaryBtn")

        self.edit.clicked.connect(self.edit_selected)
        self.delete.clicked.connect(self.delete_selected)
        self.refresh.clicked.connect(self.refresh_table)

        btn_row.addWidget(self.edit); btn_row.addWidget(self.delete); btn_row.addWidget(self.refresh); btn_row.addStretch(1)
        c.addLayout(btn_row)

        lay.addWidget(card)
        self.refresh_table()

    def update_language(self, t: Dict[str, str]):
        self.title.setText(t["stats_title"])
        self.name.setPlaceholderText(t["stats_name_placeholder"])
        self.percent_label.setText(t["stats_percent_label"])
        self.add_btn.setText(t["stats_add"])
        self.edit.setText(t["stats_edit"])
        self.delete.setText(t["stats_delete"])
        self.refresh.setText(t["stats_refresh"])

    def add_hamster(self):
        name = self.name.text().strip()
        if not name:
            show_message(self, "Ошибка", "Введите название хомяка.")
            return
        self.ui.hamsters[name] = {"percent": int(self.percent.value())}
        self.ui.save_hamsters()
        self.name.clear()
        self.refresh_table()
        self.ui.auto_page_update_hamsters()

    def refresh_table(self):
        counts = {}
        csv_path = self.ui.cfg.tokens_csv_path()
        if csv_path.exists():
            try:
                with open(csv_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        h = (row.get("hamster") or "None").strip() or "None"
                        counts[h] = counts.get(h, 0) + 1
            except Exception:
                pass

        self.table.setRowCount(0)
        for name, meta in self.ui.hamsters.items():
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(name))
            self.table.setItem(r, 1, QTableWidgetItem(str(meta.get("percent", 0))))
            self.table.setItem(r, 2, QTableWidgetItem(str(counts.get(name, 0))))

    def edit_selected(self):
        r = self.table.currentRow()
        if r < 0:
            return
        name = self.table.item(r,0).text()
        percent = safe_int(self.table.item(r,1).text(), 50)

        dlg = StyledDialog(self, "Редактировать хомяка")
        dlg.resize(720, 320)

        def _lbl(t: str) -> QLabel:
            l = QLabel(t)
            l.setWordWrap(True)
            l.setMinimumWidth(380)
            l.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            return l

        form = QFormLayout()
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(14)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        wname = QLineEdit(name); wname.setObjectName("Input")
        wperc = QSpinBox(); wperc.setRange(0,100); wperc.setValue(percent); wperc.setObjectName("Input")
        form.addRow("Название:", wname)
        form.addRow("Процент:", wperc)
        dlg.body.addLayout(form)

        row = QHBoxLayout()
        ok = QPushButton("Сохранить"); ok.setObjectName("PrimaryBtn")
        cancel = QPushButton("Отмена"); cancel.setObjectName("SecondaryBtn")
        row.addWidget(ok); row.addWidget(cancel); row.addStretch(1)
        dlg.body.addLayout(row)

        def do_ok():
            new_name = wname.text().strip()
            if not new_name:
                return
            if new_name != name:
                self.ui.hamsters.pop(name, None)
            self.ui.hamsters[new_name] = {"percent": int(wperc.value())}
            self.ui.save_hamsters()
            dlg.accept()

        ok.clicked.connect(do_ok)
        cancel.clicked.connect(dlg.reject)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh_table()
            self.ui.auto_page_update_hamsters()

    def delete_selected(self):
        r = self.table.currentRow()
        if r < 0:
            return
        name = self.table.item(r,0).text()
        rect = self.table.visualItemRect(self.table.item(r, 0))
        def _finish():
            self.ui.hamsters.pop(name, None)
            self.ui.save_hamsters()
            self.refresh_table()
            self.ui.auto_page_update_hamsters()
        animate_evaporate_rect(self.table.viewport(), rect, _finish)

class BotFactoryApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.setWindowTitle(APP_NAME)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.resize(int(geo.width() * 0.9), int(geo.height() * 0.9))
        else:
            self.resize(1220, 740)
        self.setMinimumSize(980, 640)

        self.cfg = AutoConfig(**load_json(CONFIG_FILE, asdict(AutoConfig())))
        # Ensure tokens output files exist on startup
        ensure_file(self.cfg.tokens_txt_path())
        ensure_file(self.cfg.tokens_csv_path())
        ensure_file(self.cfg.revoked_tokens_txt_path())
        self.hamsters = load_json(HAMSTERS_FILE, {})
        if not isinstance(self.hamsters, dict):
            self.hamsters = {}
        self.image_path = ""
        self.worker: Optional[Worker] = None
        self.bot_overrides: Dict[str, Dict] = {}
        self.account_status = load_json(ACCOUNTS_STATUS_FILE, {})
        if not isinstance(self.account_status, dict):
            self.account_status = {}
        self.bridge = PromptBridge()

        root = QWidget(); self.setCentralWidget(root)
        root_lay = QVBoxLayout(root); root_lay.setContentsMargins(0,0,0,0); root_lay.setSpacing(0)
        self.root_layout = root_lay

        self.titlebar = PremiumTitleBar(self, "")
        root_lay.addWidget(self.titlebar)

        body = QHBoxLayout(); body.setContentsMargins(18,18,18,18); body.setSpacing(16)
        self.body_layout = body
        root_lay.addLayout(body)

        sidebar = QFrame(); sidebar.setObjectName("Sidebar")
        apply_shadow(sidebar, blur=34, alpha=160, offset=QPointF(0, 10))
        self.sidebar_frame = sidebar
        side = QVBoxLayout(sidebar); side.setContentsMargins(18,18,18,18); side.setSpacing(10)
        self.side_layout = side

        brand = QLabel(APP_NAME); brand.setObjectName("BrandTitle")
        by = QLabel(BYLINE); by.setObjectName("BrandBy")
        side.addWidget(brand); side.addWidget(by); side.addSpacing(10)

        self.btn_auto = QPushButton("Автоматическое создание"); self.btn_auto.setObjectName("NavBtn")
        self.btn_bots = QPushButton("Боты"); self.btn_bots.setObjectName("NavBtn")
        self.btn_accounts = QPushButton("Аккаунты"); self.btn_accounts.setObjectName("NavBtn")
        self.btn_tokens = QPushButton("Токены"); self.btn_tokens.setObjectName("NavBtn")
        self.btn_stats = QPushButton("Статистика"); self.btn_stats.setObjectName("NavBtn")
        self.btn_manage = QPushButton("Удаление / Revoke"); self.btn_manage.setObjectName("NavBtn")
        self.btn_settings = QPushButton("Настройки"); self.btn_settings.setObjectName("NavBtn")

        side.addWidget(self.btn_auto); side.addWidget(self.btn_bots); side.addWidget(self.btn_accounts); side.addWidget(self.btn_tokens); side.addWidget(self.btn_stats); side.addWidget(self.btn_manage)
        side.addStretch(1)
        side.addWidget(self.btn_settings)
        side.addSpacing(6)
        foot = QLabel("Выход: tokens.txt • tokens.csv • sessions/"); foot.setObjectName("Footer")
        side.addWidget(foot)
        body.addWidget(sidebar, 1)

        self.logbox = LogBox()
        self.stack = QStackedWidget(); self.stack.setObjectName("Stack")

        self.auto_page = AutoPage(self)
        self.bots_page = BotsPage(self)
        self.accounts_page = AccountsPage(self)
        self.tokens_page = TokensPage(self)
        self.stats_page = StatsPage(self)
        self.manage_page = ManageBotsPage(self)
        self.settings_page = SettingsPage(self)

        self.stack.addWidget(self.auto_page)
        self.stack.addWidget(self.bots_page)
        self.stack.addWidget(self.accounts_page)
        self.stack.addWidget(self.tokens_page)
        self.stack.addWidget(self.stats_page)
        self.stack.addWidget(self.manage_page)
        self.stack.addWidget(self.settings_page)

        content_wrap = QFrame(); content_wrap.setObjectName("ContentWrap")
        apply_shadow(content_wrap, blur=30, alpha=150, offset=QPointF(0, 8))
        self.content_wrap = content_wrap
        cw = QVBoxLayout(content_wrap); cw.setContentsMargins(0,0,0,0)
        self.content_layout = cw
        cw.addWidget(self.stack, 1)
        body.addWidget(content_wrap, 3)

        self.btn_auto.clicked.connect(lambda: self._nav(0))
        self.btn_bots.clicked.connect(lambda: self._nav(1))
        self.btn_accounts.clicked.connect(lambda: self._nav(2))
        self.btn_tokens.clicked.connect(lambda: self._nav(3))
        self.btn_stats.clicked.connect(lambda: self._nav(4))
        self.btn_manage.clicked.connect(lambda: self._nav(5))
        self.btn_settings.clicked.connect(lambda: self._nav(6))
        self._nav(0)

        self.bridge.request_code.connect(self._ask_code)
        self.bridge.request_password.connect(self._ask_password)

        self.setStyleSheet(self._style())
        self.animator = ActionAnimator(self)
        QApplication.instance().installEventFilter(self.animator)
        self.onboarding_overlay = OnboardingOverlay(self)
        self.onboarding_overlay.hide()
        self.apply_language(self.cfg.language)
        QTimer.singleShot(0, lambda: center_on_screen(self))
        QTimer.singleShot(200, self._maybe_first_run)
        self.auto_page_update_hamsters()

    def _style(self) -> str:
        return """
        * { font-family: "Segoe UI Variable Text", "Segoe UI", "Arial"; }
        QLabel { color: rgba(230,237,243,0.92); font-weight: 700; margin-bottom: 2px; }
        QCheckBox { color: rgba(230,237,243,0.92); font-weight: 700; spacing: 10px; }
        QCheckBox::indicator {
            width: 18px; height: 18px;
            border-radius: 6px;
            border: 1px solid rgba(255,255,255,0.20);
            background: rgba(255,255,255,0.06);
        }
        QCheckBox::indicator:checked {
            background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(50,120,255,0.95), stop:1 rgba(0,200,255,0.95));
            border: 1px solid rgba(255,255,255,0.28);
        }

        QMainWindow { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
            stop:0 rgba(6,10,20,255),
            stop:0.5 rgba(8,14,26,255),
            stop:1 rgba(10,18,32,255)); }
        #PremiumTitleBar { background: rgba(8, 12, 22, 0.98); border-bottom: 1px solid rgba(255,255,255,0.08); }
        #TitleBarText { color: rgba(230,237,243,0.90); font-weight: 900; font-size: 14px; }
        QPushButton#WinBtn, QPushButton#WinClose {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 10px;
        }
        QPushButton#WinBtn:hover { background: rgba(0, 200, 255, 0.12); border-color: rgba(0,200,255,0.22); }
        QPushButton#WinClose:hover { background: rgba(255, 83, 112, 0.18); border-color: rgba(255,83,112,0.24); }

        #Sidebar {
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                stop:0 rgba(12,18,34,0.98),
                stop:1 rgba(9,13,24,0.96));
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 24px;
        }
        #BrandTitle { color: rgba(236,242,250,0.98); font-weight: 800; font-size: 24px; letter-spacing: 0.2px; }
        #BrandBy { color: rgba(230,237,243,0.60); font-weight: 600; font-size: 12px; margin-top: -2px; }
        #Footer { color: rgba(230,237,243,0.60); font-size: 11px; font-weight: 600; }

        #ContentWrap {
            background: rgba(12,18,34,0.98);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 24px;
        }

        #Card {
            background: rgba(12,18,34,0.98);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 24px;
        }
        #PageTitle { color: rgba(236,242,250,0.98); font-size: 21px; font-weight: 800; }
        #Hint { color: rgba(230,237,243,0.70); font-size: 12px; font-weight: 600; }

        #Input {
            min-height: 36px;
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 16px;
            padding: 10px 14px;
            color: rgba(236,242,250,0.98);
            font-weight: 600;
        }
        #Input:focus { border: 1px solid rgba(120, 60, 255, 0.50); background: rgba(255,255,255,0.08); }
        QComboBox QAbstractItemView {
            background: rgba(12,18,34,0.98);
            color: rgba(236,242,250,0.98);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 16px;
            selection-background-color: rgba(120, 60, 255, 0.28);
            selection-color: rgba(236,242,250,0.98);
            padding: 6px;
            outline: 0;
        }
        QComboBox QAbstractItemView::item {
            min-height: 26px;
        }
        QComboBox::drop-down {
            width: 24px;
        }

        QMainWindow[compact="true"] #Input {
            min-height: 30px;
            padding: 8px 12px;
        }
        QMainWindow[compact="true"] #NavBtn { padding: 10px 12px; font-size: 12px; }
        QMainWindow[compact="true"] #PrimaryBtn,
        QMainWindow[compact="true"] #SecondaryBtn { padding: 8px 12px; font-size: 12px; }
        QMainWindow[compact="true"] #PageTitle { font-size: 19px; }
        QMainWindow[compact="true"] #Hint { font-size: 11px; }

        #NavBtn {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 18px;
            padding: 12px 14px;
            color: rgba(236,242,250,0.94);
            font-weight: 700;
            text-align: left;
        }
        #NavBtn:hover { background: rgba(120, 60, 255, 0.08); }
        #NavBtn[active="true"] {
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 rgba(120, 60, 255, 0.24),
                stop:1 rgba(0, 200, 255, 0.20));
            border: 1px solid rgba(120, 60, 255, 0.30);
        }
        #NavBtn:disabled {
            color: rgba(236,242,250,0.72);
        }
        #NavBtn[active="true"]:disabled {
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 rgba(120, 60, 255, 0.24),
                stop:1 rgba(0, 200, 255, 0.20));
            border: 1px solid rgba(120, 60, 255, 0.30);
            color: rgba(236,242,250,0.90);
        }
        #NavBtn[onboarding="true"] {
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 rgba(255, 80, 160, 0.32),
                stop:0.5 rgba(120, 120, 255, 0.30),
                stop:1 rgba(0, 200, 255, 0.32));
            border: 1px solid rgba(120, 180, 255, 0.55);
        }

        #PrimaryBtn {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(66,146,255,0.98), stop:0.5 rgba(146,86,255,0.98), stop:1 rgba(0,210,255,0.98));
            border: 1px solid rgba(255,255,255,0.14);
            border-radius: 18px;
            padding: 10px 16px;
            color: rgba(255,255,255,0.98);
            font-weight: 700;
        }
        #PrimaryBtn:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 rgba(60,140,255,0.98), stop:0.5 rgba(150,80,255,0.98), stop:1 rgba(0,210,255,0.98)); }

        #SecondaryBtn {
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 18px;
            padding: 10px 16px;
            color: rgba(236,242,250,0.96);
            font-weight: 600;
        }
        #SecondaryBtn:hover { background: rgba(255,255,255,0.10); }
        #EmojiBtn {
            background: rgba(255,255,255,0.10);
            border: 1px solid rgba(255,255,255,0.14);
            border-radius: 14px;
            padding: 6px 10px;
            color: rgba(230,237,243,0.95);
            font-weight: 900;
        }
        #EmojiBtn:hover { background: rgba(255,255,255,0.18); }

        QScrollBar:vertical {
            background: transparent;
            width: 10px;
            margin: 6px 4px 6px 4px;
        }
        QScrollBar::handle:vertical {
            background: rgba(120,160,255,0.35);
            border-radius: 5px;
            min-height: 40px;
        }
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical { height: 0px; }
        QScrollBar:horizontal {
            background: transparent;
            height: 10px;
            margin: 4px 6px 4px 6px;
        }
        QScrollBar::handle:horizontal {
            background: rgba(120,160,255,0.35);
            border-radius: 5px;
            min-width: 40px;
        }
        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal { width: 0px; }

        QTreeWidget::item { color: rgba(230,237,243,0.92); font-weight: 900; }
        QTreeWidget::item:selected { background: rgba(120, 60, 255, 0.20); }
        QTreeWidget::item:alternate { background: rgba(255,255,255,0.03); }
        QTreeWidget QAbstractScrollArea::corner { background: rgba(18,26,46,0.85); border: none; border-radius: 16px; }
        QTreeView::corner { background: rgba(18,26,46,0.85); border: none; border-radius: 16px; }
        QTableView::corner { background: rgba(18,26,46,0.85); border: none; border-radius: 16px; }
        QTableCornerButton::section { background: rgba(18,26,46,0.85); border: none; border-radius: 16px; }
        QTreeWidget::indicator {
            width: 16px;
            height: 16px;
            border-radius: 4px;
            border: 1px solid rgba(255,255,255,0.20);
            background: rgba(255,255,255,0.06);
        }
        QTreeWidget::indicator:checked {
            background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                stop:0 rgba(50,120,255,0.95),
                stop:1 rgba(0,200,255,0.95));
            border: 1px solid rgba(255,255,255,0.28);
        }
        QSpinBox {
            min-height: 36px;
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 16px;
            padding: 4px 10px;
            color: rgba(236,242,250,0.98);
            font-weight: 600;
        }
        QSpinBox::up-button, QSpinBox::down-button {
            subcontrol-origin: border;
            background: rgba(255,255,255,0.06);
            border: none;
            width: 16px;
        }
        QSpinBox::up-button { subcontrol-position: top right; border-top-right-radius: 12px; }
        QSpinBox::down-button { subcontrol-position: bottom right; border-bottom-right-radius: 12px; }

        #LogBox {
            background: rgba(8, 12, 22, 0.55);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 22px;
        }
        #LogText { color: rgba(236,242,250,0.90); font-weight: 600; font-size: 12px; }

        #StatsTable {
            background: rgba(8, 12, 22, 0.40);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 16px;
            color: rgba(236,242,250,0.92);
            gridline-color: rgba(255,255,255,0.06);
        }
        QTableWidget::item {
            padding: 6px 10px;
            background: transparent;
        }
        QTableWidget::item:alternate {
            background: rgba(255,255,255,0.03);
        }
        QTableWidget::item:selected {
            background: rgba(120, 60, 255, 0.20);
        }
        QTableWidget, QTreeWidget, QTableView, QTreeView, QAbstractScrollArea {
            border-radius: 16px;
            background: rgba(8, 12, 22, 0.35);
        }
        QTableView::viewport, QTreeView::viewport, QAbstractScrollArea::viewport {
            border-radius: 16px;
            background: transparent;
        }
        QHeaderView::section {
            background: rgba(8, 12, 22, 0.80);
            color: rgba(230,237,243,0.80);
            border: none;
            padding: 8px;
            font-weight: 700;
            border-radius: 16px;
        }
        QHeaderView::section:first {
            border-top-left-radius: 16px;
        }
        QHeaderView::section:last {
            border-top-right-radius: 16px;
        }

        QDialog#PremiumDialog { background: transparent; }
        #PremiumDialogCard {
            background: rgba(8, 12, 22, 0.98);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 22px;
        }
        #PremiumDialogTitle { color: rgba(230,237,243,0.95); font-weight: 1000; font-size: 14px; }

        #FirstRunCard {
            background: rgba(8, 12, 22, 0.98);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 24px;
        }
        #OnboardingOverlay {
            background: transparent;
        }
        #OverlayCard {
            background: rgba(10, 16, 30, 0.98);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 24px;
            min-width: 520px;
            max-width: 860px;
            min-height: 320px;
        }
        #OverlayTitle { color: rgba(230,237,243,0.98); font-size: 18px; font-weight: 1000; }
        #OverlayText { color: rgba(230,237,243,0.88); font-size: 13px; font-weight: 800; }
        

        /* --- Customization dialog background consistency --- */
        QDialog#StyledDialog {
            background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                stop:0 rgba(8,12,24,255),
                stop:1 rgba(12,18,40,255));
        }
        QScrollArea { background: transparent; }
        QAbstractScrollArea::viewport { background: transparent; }
        QScrollArea QWidget { background: transparent; }
    """

    def _nav(self, idx: int):
        self.stack.setCurrentIndex(idx)
        btns = [self.btn_auto, self.btn_bots, self.btn_accounts, self.btn_tokens, self.btn_stats, self.btn_manage, self.btn_settings]
        for i, b in enumerate(btns):
            is_active = i == idx
            b.setProperty("active", "true" if is_active else "false")
            b.setEnabled(not is_active)
            b.style().unpolish(b)
            b.style().polish(b)
        try:
            self.stack.currentWidget().setGraphicsEffect(None)
        except Exception:
            pass
        animate_section_fade(self.stack.currentWidget(), 180)

    def _maybe_first_run(self):
        if getattr(self.cfg, "first_run_done", False):
            return
        dlg = FirstRunDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.cfg.first_run_done = True
            self.cfg.language = dlg.selected_language
            self.save_config()
            if dlg.launch_onboarding:
                QTimer.singleShot(200, self.open_onboarding)

    def open_onboarding(self):
        steps = self._onboarding_steps()
        def _sync_section(idx: int):
            targets = [self.btn_auto, self.btn_bots, self.btn_accounts, self.btn_tokens, self.btn_stats, self.btn_manage]
            if idx < len(targets):
                self._nav(idx)
                self.onboarding_overlay.set_target_widget(targets[idx])
            else:
                self.onboarding_overlay.set_target_widget(None)
        self.onboarding_overlay.on_step_changed = _sync_section
        self.onboarding_overlay.set_steps(steps)
        self.onboarding_overlay.open_overlay()
        self.onboarding_overlay.raise_()
        _sync_section(0)

    def _onboarding_steps(self) -> List[Tuple[str, str]]:
        t = self._translations().get(self.cfg.language, self._translations()["Русский"])
        return [
            (t["onb_auto_title"], t["onb_auto_body"]),
            (t["onb_bots_title"], t["onb_bots_body"]),
            (t["onb_accounts_title"], t["onb_accounts_body"]),
            (t["onb_tokens_title"], t["onb_tokens_body"]),
            (t["onb_stats_title"], t["onb_stats_body"]),
            (t["onb_manage_title"], t["onb_manage_body"]),
            (t["onb_final_title"], t["onb_final_body"]),
        ]

    def resizeEvent(self, event):
        w = self.width()
        h = self.height()
        compact = w < 1200 or h < 760
        self.setProperty("compact", "true" if compact else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        if compact:
            self.body_layout.setContentsMargins(10, 10, 10, 10)
            self.body_layout.setSpacing(10)
            self.side_layout.setContentsMargins(12, 12, 12, 12)
            self.side_layout.setSpacing(8)
            self.sidebar_frame.setFixedWidth(250)
            self.body_layout.setStretch(0, 1)
            self.body_layout.setStretch(1, 4)
            self.logbox.text.setMaximumHeight(170)
        else:
            self.body_layout.setContentsMargins(18, 18, 18, 18)
            self.body_layout.setSpacing(16)
            self.side_layout.setContentsMargins(18, 18, 18, 18)
            self.side_layout.setSpacing(10)
            self.sidebar_frame.setMinimumWidth(0)
            self.sidebar_frame.setMaximumWidth(16777215)
            self.body_layout.setStretch(0, 1)
            self.body_layout.setStretch(1, 3)
            self.logbox.text.setMaximumHeight(220)
        if hasattr(self, "onboarding_overlay") and self.onboarding_overlay.isVisible():
            self.onboarding_overlay.setGeometry(self.rect())
        super().resizeEvent(event)

    def save_config(self):
        save_json(CONFIG_FILE, asdict(self.cfg))

    def save_account_status(self):
        save_json(ACCOUNTS_STATUS_FILE, self.account_status)

    def save_hamsters(self):
        save_json(HAMSTERS_FILE, self.hamsters)

    def auto_page_update_hamsters(self):
        self.auto_page.hamster.clear()
        self.auto_page.hamster.addItem("None")
        for name in sorted(self.hamsters.keys()):
            self.auto_page.hamster.addItem(name)

    def log(self, s: str):
        self.logbox.append(s)

    def _translations(self) -> Dict[str, Dict[str, str]]:
        return {
            "Русский": {
                "nav_auto": "Автоматическое создание",
                "nav_bots": "Боты",
                "nav_accounts": "Аккаунты",
                "nav_tokens": "Токены",
                "nav_stats": "Статистика",
                "nav_manage": "Удаление / Revoke",
                "nav_settings": "Настройки",
                "auto_title": "Автоматическое создание",
                "auto_chat": "Чат:",
                "auto_names": "Имена:",
                "auto_hamster": "Хомяк:",
                "auto_names_placeholder": "name/name2/name3 (без пробелов)",
                "auto_pick_img": "Выбрать аватарку (обязательно)",
                "auto_open_tokens": "Открыть tokens.txt",
                "auto_limit_edit": "Изменить лимит",
                "auto_limit_hint": "Лимит: {limit} бота(ов) на аккаунт за 1 запуск (1 запуск = 1 круг).",
                "auto_custom": "Кастомизация (all bots)",
                "auto_edit": "Изменить (one bot)",
                "auto_start": "Запуск (Авто режим)",
                "auto_stop": "Стоп",
                "bots_title": "Боты",
                "bots_hint": "Список ботов и аккаунтов, на которых они созданы.",
                "bots_refresh": "Обновить",
                "accounts_title": "Аккаунты",
                "accounts_hint": "Управление аккаунтами и авторизацией.",
                "accounts_add": "Добавить аккаунты",
                "accounts_delete": "Удалить аккаунт",
                "accounts_auth_all": "Авторизовать все",
                "accounts_auth_failed": "Авторизовать ошибки",
                "accounts_refresh": "Обновить",
                "tokens_title": "Токены",
                "tokens_hint": "Токены сгруппированы по датам. Можно копировать, редактировать и удалять.",
                "tokens_placeholder": "Токены для выбранной даты (по одному в строке)...",
                "tokens_refresh": "Обновить",
                "tokens_save": "Сохранить изменения",
                "tokens_copy_selected": "Копировать выбранные",
                "tokens_copy_latest": "Копировать последние",
                "tokens_delete_selected": "Удалить выбранные",
                "tokens_clear": "Очистить список",
                "stats_title": "Статистика",
                "stats_name_placeholder": "Название хомяка",
                "stats_percent_label": "Процент:",
                "stats_add": "Добавить хомяка",
                "stats_edit": "Редактировать",
                "stats_delete": "Удалить выбранный",
                "stats_refresh": "Обновить",
                "manage_title": "Удаление и Revoke Token",
                "manage_hint": "Выберите ботов в таблице для массового удаления или revoke токена.",
                "manage_refresh": "Обновить список",
                "manage_delete_mass": "Массовое удаление",
                "manage_delete_single": "Единичное удаление",
                "manage_revoke_mass": "Массовый Revoke",
                "manage_revoke_single": "Revoke Token",
                "manage_open_revoked": "Открыть revoke_tokens.txt",
                "settings_title": "Настройки",
                "settings_hint": "",
                "settings_language": "Язык:",
                "settings_autostart_label": "Автозапуск с Windows:",
                "settings_autostart_toggle": "Включить автозапуск",
                "settings_backup": "Создать резервную копию",
                "settings_restore": "Импорт резервной копии",
                "settings_reset": "Сброс до заводских настроек",
                "settings_onboarding": "Мастер новичка",
                "settings_support": "Тех. Поддержка",
                "onb_auto_title": "Авто‑создание",
                "onb_auto_body": "• Имена вводите через «/», например: name1/name2/name3.\n• Выберите хомяка — используйте если ботов нашел другой человек\n• Выберите картинку, которая будет назначена всем создаваемым ботам.\n• Нажмите «Запуск (Авто режим)».\n• Лимит ботов на аккаунт можно менять здесь же.",
                "onb_bots_title": "Боты",
                "onb_bots_body": "• Здесь список созданных ботов.\n• Видно аккаунт, на котором создан бот, и дату создания.\n• Нажмите «Обновить», чтобы подтянуть свежие данные после запуска.",
                "onb_accounts_title": "Аккаунты",
                "onb_accounts_body": "• Добавляйте аккаунты в формате phone:password:api_id:api_hash.\n• Используйте «Авторизовать все», чтобы проверить вход.\n• «Авторизовать ошибки» — только проблемные аккаунты.\n• Статусы показывают причину ошибок.",
                "onb_tokens_title": "Токены",
                "onb_tokens_body": "• Токены сгруппированы по датам.\n• Раскрывайте дату стрелкой, чтобы увидеть токены.\n• Копируйте выбранные группы, редактируйте и удаляйте записи.",
                "onb_stats_title": "Статистика",
                "onb_stats_body": "• Создавайте хомяков с учетом их доли от заработка с ботов в процентах.\n• Просмотр кол-ва ботов по каждому хомяку.\n• Можно редактировать и удалять записи.",
                "onb_manage_title": "Удаление / Revoke",
                "onb_manage_body": "• Выберите ботов в таблице.\n• Массовое удаление — удаляет всех выбранных ботов.\n• Единичное удаление — удаляет выбранного бота.\n• Revoke Token — получает новый токен и сохраняет в revoke_tokens.txt.",
                "onb_final_title": "Финал",
                "onb_final_body": "Поздравляю, теперь ты знаешь базовые функции этого приложения!🎉\n\ncreated by whynot"
            },
            "English": {
                "nav_auto": "Auto creation",
                "nav_bots": "Bots",
                "nav_accounts": "Accounts",
                "nav_tokens": "Tokens",
                "nav_stats": "Stats",
                "nav_manage": "Delete / Revoke",
                "nav_settings": "Settings",
                "auto_title": "Auto creation",
                "auto_chat": "Chat:",
                "auto_names": "Names:",
                "auto_hamster": "Hamster:",
                "auto_names_placeholder": "name/name2/name3 (no spaces preferred)",
                "auto_pick_img": "Pick image (required)",
                "auto_open_tokens": "Open tokens.txt",
                "auto_limit_edit": "Change limit",
                "auto_limit_hint": "Limit: {limit} bot(s) per account per run (1 run = 1 round).",
                "auto_custom": "Customization",
                "auto_edit": "Edit",
                "auto_start": "Start (Auto mode)",
                "auto_stop": "Stop",
                "bots_title": "Bots",
                "bots_hint": "List of bots and the accounts they were created on.",
                "bots_refresh": "Refresh",
                "accounts_title": "Accounts",
                "accounts_hint": "Manage accounts and authorization.",
                "accounts_add": "Add accounts",
                "accounts_delete": "Delete account",
                "accounts_auth_all": "Authorize all",
                "accounts_auth_failed": "Authorize failed",
                "accounts_refresh": "Refresh",
                "tokens_title": "Tokens",
                "tokens_hint": "Tokens are grouped by dates. You can copy, edit, and delete them.",
                "tokens_placeholder": "Tokens for the selected date (one per line)...",
                "tokens_refresh": "Refresh",
                "tokens_save": "Save changes",
                "tokens_copy_selected": "Copy selected",
                "tokens_copy_latest": "Copy latest",
                "tokens_delete_selected": "Delete selected",
                "tokens_clear": "Clear list",
                "stats_title": "Stats",
                "stats_name_placeholder": "Hamster name",
                "stats_percent_label": "Percent:",
                "stats_add": "Add hamster",
                "stats_edit": "Edit",
                "stats_delete": "Delete selected",
                "stats_refresh": "Refresh",
                "manage_title": "Delete and Revoke Token",
                "manage_hint": "Select bots in the table for deletion or token revoke.",
                "manage_refresh": "Refresh list",
                "manage_delete_mass": "Mass delete",
                "manage_delete_single": "Single delete",
                "manage_revoke_mass": "Mass revoke",
                "manage_revoke_single": "Revoke token",
                "manage_open_revoked": "Open revoke_tokens.txt",
                "settings_title": "Settings",
                "settings_hint": "Manage language, autostart, and backups.",
                "settings_language": "Language:",
                "settings_autostart_label": "Autostart with Windows:",
                "settings_autostart_toggle": "Enable autostart",
                "settings_backup": "Create backup",
                "settings_restore": "Import backup",
                "settings_reset": "Factory reset",
                "settings_onboarding": "Onboarding wizard",
                "settings_support": "Support",
                "onb_auto_title": "Auto creation",
                "onb_auto_body": "• Enter names using “/”, e.g., name1/name2/name3.\n• Choose a hamster — use this if the bots were found by another person.\n• Choose an image that will be assigned to all created bots.\n• Click “Start (Auto mode)”.\n• Account bot limit can be changed here.",
                "onb_bots_title": "Bots",
                "onb_bots_body": "• List of created bots.\n• Shows the account and creation date.\n• Click “Refresh” to sync new data.",
                "onb_accounts_title": "Accounts",
                "onb_accounts_body": "• Add accounts as phone:password:api_id:api_hash.\n• Use “Authorize all” to check login.\n• “Authorize failed” checks only problematic accounts.\n• Statuses show error reasons.",
                "onb_tokens_title": "Tokens",
                "onb_tokens_body": "• Tokens are grouped by date.\n• Expand a date to see tokens.\n• Copy, edit, or delete groups.",
                "onb_stats_title": "Stats",
                "onb_stats_body": "• Create hamsters with percentages.\n• See bot count per hamster.\n• You can edit or delete entries.",
                "onb_manage_title": "Delete / Revoke",
                "onb_manage_body": "• Select bots in the table.\n• Mass delete removes all selected bots.\n• Single delete removes the selected bot.\n• Revoke token generates a new token and saves it to revoke_tokens.txt.",
                "onb_final_title": "Finish",
                "onb_final_body": "Congrats, you now know the main features of this app!🎉\n\ncreated by whynot_repow"
            }
        }

    def apply_language(self, lang: str):
        t = self._translations().get(lang, self._translations()["Русский"])
        self.btn_auto.setText(t["nav_auto"])
        self.btn_bots.setText(t["nav_bots"])
        self.btn_accounts.setText(t["nav_accounts"])
        self.btn_tokens.setText(t["nav_tokens"])
        self.btn_stats.setText(t["nav_stats"])
        self.btn_manage.setText(t["nav_manage"])
        self.btn_settings.setText(t["nav_settings"])
        self.auto_page.update_language(t)
        self.bots_page.update_language(t)
        self.accounts_page.update_language(t)
        self.tokens_page.update_language(t)
        self.stats_page.update_language(t)
        self.manage_page.update_language(t)
        self.settings_page.update_language(t)
        self.auto_page.update_limit_hint()

    def format_limit_hint(self, limit: int) -> str:
        t = self._translations().get(self.cfg.language, self._translations()["Русский"])
        return t["auto_limit_hint"].format(limit=limit)

    def set_language(self, lang: str):
        self.cfg.language = lang
        self.save_config()
        self.apply_language(lang)

    def pick_image(self):
        p, _ = QFileDialog.getOpenFileName(self, "Выбрать аватарку", str(BASE_DIR), "Images (*.png *.jpg *.jpeg *.webp)")
        if p:
            self.image_path = p
            self.log(f"[OK] Картинка: {p}")

    def open_tokens_txt(self):
        path = self.cfg.tokens_txt_path()
        ensure_file(path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def open_revoked_tokens_txt(self):
        path = self.cfg.revoked_tokens_txt_path()
        ensure_file(path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _startup_bat_path(self) -> Optional[Path]:
        if not sys.platform.startswith("win"):
            return None
        startup_dir = Path(os.getenv("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        return startup_dir / "BotFactory_Autostart.bat"

    def is_autostart_enabled(self) -> bool:
        bat_path = self._startup_bat_path()
        return bool(bat_path and bat_path.exists())

    def toggle_autostart(self, enabled: bool):
        bat_path = self._startup_bat_path()
        if not bat_path:
            show_message(self, "Автозапуск", "Автозапуск доступен только в Windows.")
            if self.settings_page:
                self.settings_page.autostart_toggle.setChecked(False)
            return
        try:
            if enabled:
                bat_path.parent.mkdir(parents=True, exist_ok=True)
                cmd = f"@echo off\ncd /d \"{BASE_DIR}\"\n\"{sys.executable}\" \"{BASE_DIR / 'app.py'}\"\n"
                bat_path.write_text(cmd, encoding="utf-8")
                show_message(self, "Автозапуск", "Автозапуск включён.")
            else:
                if bat_path.exists():
                    bat_path.unlink()
                show_message(self, "Автозапуск", "Автозапуск отключён.")
        except Exception as e:
            show_message(self, "Автозапуск", f"Ошибка автозапуска: {e}")
            if self.settings_page:
                self.settings_page.autostart_toggle.setChecked(self.is_autostart_enabled())

    def create_backup(self):
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить резервную копию", str(BASE_DIR / "backup.zip"), "ZIP (*.zip)")
        if not path:
            return
        try:
            files = [
                CONFIG_FILE,
                ACCOUNTS_FILE,
                HAMSTERS_FILE,
                FROZEN_FILE,
                ACCOUNTS_STATUS_FILE,
                self.cfg.tokens_txt_path(),
                self.cfg.tokens_csv_path(),
                self.cfg.revoked_tokens_txt_path(),
            ]
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in files:
                    if f.exists():
                        zf.write(f, f.relative_to(BASE_DIR))
                if SESSIONS_DIR.exists():
                    for root, _, filenames in os.walk(SESSIONS_DIR):
                        for fname in filenames:
                            full = Path(root) / fname
                            zf.write(full, full.relative_to(BASE_DIR))
            show_message(self, "Резервная копия", "Резервная копия создана.")
        except Exception as e:
            show_message(self, "Резервная копия", f"Ошибка создания: {e}")

    def restore_backup(self):
        path, _ = QFileDialog.getOpenFileName(self, "Импорт резервной копии", str(BASE_DIR), "ZIP (*.zip)")
        if not path:
            return
        try:
            with zipfile.ZipFile(path, "r") as zf:
                zf.extractall(BASE_DIR)
            show_message(self, "Импорт резервной копии", "Резервная копия импортирована. Перезапустите приложение.")
        except Exception as e:
            show_message(self, "Импорт резервной копии", f"Ошибка импорта: {e}")

    def reset_factory(self):
        try:
            for f in [CONFIG_FILE, ACCOUNTS_FILE, HAMSTERS_FILE, FROZEN_FILE, ACCOUNTS_STATUS_FILE,
                      self.cfg.tokens_txt_path(), self.cfg.tokens_csv_path(), self.cfg.revoked_tokens_txt_path()]:
                if f.exists():
                    f.unlink()
            if SESSIONS_DIR.exists():
                shutil.rmtree(SESSIONS_DIR, ignore_errors=True)
            ensure_file(self.cfg.tokens_txt_path())
            ensure_file(self.cfg.tokens_csv_path())
            ensure_file(self.cfg.revoked_tokens_txt_path())
            show_message(self, "Сброс", "Настройки сброшены. Перезапустите приложение.")
        except Exception as e:
            show_message(self, "Сброс", f"Ошибка сброса: {e}")

    def open_support(self):
        QDesktopServices.openUrl(QUrl("https://t.me/whynot_repow"))

    def _selected_manage_targets(self) -> List[Dict[str, str]]:
        return self.manage_page.selected_targets()

    def delete_mass(self):
        if self.worker and self.worker.isRunning():
            show_message(self, "Уже работает", "Сначала остановите текущий процесс.")
            return
        targets = self._selected_manage_targets()
        if not targets:
            show_message(self, "Ошибка", "Выберите ботов в таблице для массового удаления.")
            return
        self.log(f"[INFO] Массовое удаление: {len(targets)} ботов.")
        self.worker = Worker(
            "delete",
            self.cfg.botfather,
            [],
            "None",
            "",
            self.cfg,
            self.bridge,
            self.bot_overrides,
            self.account_status,
            delete_targets=targets
        )
        self.worker.log.connect(self.log)
        self.worker.progress.connect(self.log)
        self.worker.start()

    def delete_single(self):
        if self.worker and self.worker.isRunning():
            show_message(self, "Уже работает", "Сначала остановите текущий процесс.")
            return
        targets = self._selected_manage_targets()
        if len(targets) != 1:
            show_message(self, "Ошибка", "Выберите одного бота для единичного удаления.")
            return
        self.log(f"[INFO] Единичное удаление: @{targets[0]['username']}.")
        self.worker = Worker(
            "delete",
            self.cfg.botfather,
            [],
            "None",
            "",
            self.cfg,
            self.bridge,
            self.bot_overrides,
            self.account_status,
            delete_targets=targets
        )
        self.worker.log.connect(self.log)
        self.worker.progress.connect(self.log)
        self.worker.start()

    def revoke_token(self):
        if self.worker and self.worker.isRunning():
            show_message(self, "Уже работает", "Сначала остановите текущий процесс.")
            return
        targets = self._selected_manage_targets()
        if len(targets) != 1:
            show_message(self, "Ошибка", "Выберите одного бота для revoke token.")
            return
        self.log(f"[INFO] Revoke token: @{targets[0]['username']}.")
        self.worker = Worker(
            "revoke",
            self.cfg.botfather,
            [],
            "None",
            "",
            self.cfg,
            self.bridge,
            self.bot_overrides,
            self.account_status,
            revoke_targets=targets
        )
        self.worker.log.connect(self.log)
        self.worker.progress.connect(self.log)
        self.worker.finished_ok.connect(self._on_revoke_finished)
        self.worker.start()

    def revoke_mass(self):
        if self.worker and self.worker.isRunning():
            show_message(self, "Уже работает", "Сначала остановите текущий процесс.")
            return
        targets = self._selected_manage_targets()
        if not targets:
            show_message(self, "Ошибка", "Выберите ботов для массового revoke.")
            return
        self.log(f"[INFO] Массовый revoke: {len(targets)} ботов.")
        self.worker = Worker(
            "revoke",
            self.cfg.botfather,
            [],
            "None",
            "",
            self.cfg,
            self.bridge,
            self.bot_overrides,
            self.account_status,
            revoke_targets=targets
        )
        self.worker.log.connect(self.log)
        self.worker.progress.connect(self.log)
        self.worker.finished_ok.connect(self._on_revoke_finished)
        self.worker.start()

    def _ask_code(self, phone: str):
        code = show_input_dialog(self, "Код авторизации", f"Введите код для {phone}:")
        self.bridge.set_code(code or "")

    def _ask_password(self, phone: str):
        pwd = show_input_dialog(self, "Пароль 2FA", f"Введите пароль 2FA для {phone}:", echo_mode=QLineEdit.EchoMode.Password)
        self.bridge.set_password(pwd or "")

    def stop_worker(self):
        if self.worker:
            self.worker.stop()
            self.log("[INFO] Stop запрошен.")

    def _on_auto_finished(self):
        worker = self.worker
        if not worker or worker.mode != "auto":
            return
        if worker.too_many_phones:
            phones = ", ".join(sorted(worker.too_many_phones))
            show_message(self, "Лимит ботов", f"На аккаунтах достигнут лимит 20 ботов: {phones}")
        if worker.no_available_accounts:
            remaining = worker.remaining_names or []
            rest = "/".join(remaining)
            show_copy_dialog(
                self,
                "Нет доступных аккаунтов",
                "Бот не смог создать ни одного бота за 3 круга аккаунтов.\nОстаток имён для создания:",
                rest
            )

    def _on_revoke_finished(self):
        worker = self.worker
        if not worker or worker.mode != "revoke":
            return
        if not worker.revoked_results:
            show_message(self, "Revoke завершён", "Токены не были получены.")
            return
        lines = [f"@{name}: {token}" for name, token in worker.revoked_results]
        show_copy_dialog(
            self,
            "Revoke завершён",
            "Операция завершена. Полученные токены:",
            "\n".join(lines)
        )


    def open_customization(self):
        # Полностью адаптивная кастомизация: не ломается на любом разрешении (DPI/Scale)
        dlg = StyledDialog(self, "Кастомизация авто-режима")
        dlg.resize(1100, 700)
        dlg.setMinimumSize(900, 600)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        scroll.setWidget(container)

        main = QVBoxLayout(container)
        main.setContentsMargins(20, 20, 20, 20)
        main.setSpacing(24)

        def section(title: str):
            card = QFrame()
            card.setObjectName("Card")
            lay = QVBoxLayout(card)
            lay.setContentsMargins(20, 20, 20, 20)
            lay.setSpacing(14)

            lbl = QLabel(title)
            lbl.setStyleSheet("font-size:18px;font-weight:1000;")
            lay.addWidget(lbl)
            return card, lay

        # --- ИМЯ БОТА ---
        card, lay = section("Имя бота (видимое в Telegram)")
        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)

        w_prefix = QLineEdit(getattr(self.cfg, "name_prefix", ""))
        w_suffix = QLineEdit(getattr(self.cfg, "name_suffix", ""))

        w_prefix.setObjectName("Input")
        w_suffix.setObjectName("Input")

        form.addRow("Префикс (будет ПЕРЕД СУФФИКСОМ):", w_prefix)
        form.addRow("Суффикс (БУДЕТ ПОСЛЕ ПРЕФИКСА):", w_suffix)

        lay.addLayout(form)
        main.addWidget(card)

        # --- USERNAME ---
        card, lay = section("Username бота (адрес @...)")
        form = QFormLayout()
        form.setSpacing(12)

        w_user_suffix = QLineEdit(getattr(self.cfg, "username_suffix", "_bot"))
        w_sep = QLineEdit(getattr(self.cfg, "numbered_separator", "_"))
        w_num = QLineEdit(getattr(self.cfg, "numbered_suffix", "bot"))

        w_max = QSpinBox()
        w_max.setRange(1, 25)
        w_max.setValue(int(getattr(self.cfg, "max_number_attempts", 5)))

        for w in (w_user_suffix, w_sep, w_num, w_max):
            w.setObjectName("Input")

        w_sanitize = QCheckBox("Автоматически приводить username к допустимому виду (латиница/цифры/_)")
        w_sanitize.setChecked(bool(getattr(self.cfg, "sanitize_username", True)))

        form.addRow("Окончание (пример: cat + _bot → cat_bot):", w_user_suffix)
        form.addRow("Разделитель перед номером (пример: cat_1bot):", w_sep)
        form.addRow("Текст после номера (пример: cat_1bot):", w_num)
        form.addRow("Сколько вариантов с номером пробовать:", w_max)
        form.addRow("", w_sanitize)

        lay.addLayout(form)
        main.addWidget(card)

        # --- ТОКЕНЫ ---
        card, lay = section("Сохранение токенов")
        form = QFormLayout()
        form.setSpacing(12)

        def _get_txt():
            if hasattr(self.cfg, "tokens_txt_path"):
                try:
                    return str(self.cfg.tokens_txt_path())
                except Exception:
                    pass
            return str(getattr(self.cfg, "tokens_txt", "tokens.txt"))

        def _get_csv():
            if hasattr(self.cfg, "tokens_csv_path"):
                try:
                    return str(self.cfg.tokens_csv_path())
                except Exception:
                    pass
            return str(getattr(self.cfg, "tokens_csv", "tokens.csv"))

        w_txt = QLineEdit(_get_txt())
        w_csv = QLineEdit(_get_csv())
        w_txt.setReadOnly(True)
        w_csv.setReadOnly(True)
        w_txt.setObjectName("Input")
        w_csv.setObjectName("Input")

        btn_txt = QPushButton("Изменить")
        btn_csv = QPushButton("Изменить")
        btn_txt.setObjectName("PrimaryBtn")
        btn_csv.setObjectName("PrimaryBtn")
        btn_txt.setFixedHeight(44)
        btn_csv.setFixedHeight(44)
        btn_txt.setMinimumWidth(180)
        btn_csv.setMinimumWidth(180)

        def pick_txt():
            p, _ = QFileDialog.getSaveFileName(self, "Куда сохранить tokens.txt", w_txt.text(), "Text (*.txt)")
            if p:
                w_txt.setText(p)

        def pick_csv():
            p, _ = QFileDialog.getSaveFileName(self, "Куда сохранить tokens.csv", w_csv.text(), "CSV (*.csv)")
            if p:
                w_csv.setText(p)

        btn_txt.clicked.connect(pick_txt)
        btn_csv.clicked.connect(pick_csv)

        row1 = QHBoxLayout()
        row1.setSpacing(12)
        row1.addWidget(w_txt, 1)
        row1.addWidget(btn_txt)

        row2 = QHBoxLayout()
        row2.setSpacing(12)
        row2.addWidget(w_csv, 1)
        row2.addWidget(btn_csv)

        form.addRow("tokens.txt (только токены):", row1)
        form.addRow("tokens.csv (для статистики):", row2)

        lay.addLayout(form)
        main.addWidget(card)

        # --- КНОПКИ ---
        btns = QHBoxLayout()
        btns.addStretch(1)

        apply_btn = QPushButton("Применить")
        close_btn = QPushButton("Закрыть")
        apply_btn.setObjectName("PrimaryBtn")
        close_btn.setObjectName("SecondaryBtn")
        apply_btn.setFixedHeight(46)
        close_btn.setFixedHeight(46)
        apply_btn.setMinimumWidth(180)
        close_btn.setMinimumWidth(180)

        btns.addWidget(apply_btn)
        btns.addWidget(close_btn)
        main.addLayout(btns)

        dlg.body.addWidget(scroll)

        def apply():
            self.cfg.name_prefix = w_prefix.text()
            self.cfg.name_suffix = w_suffix.text()
            self.cfg.username_suffix = w_user_suffix.text()
            self.cfg.numbered_separator = w_sep.text()
            self.cfg.numbered_suffix = w_num.text()
            self.cfg.max_number_attempts = w_max.value()
            self.cfg.sanitize_username = w_sanitize.isChecked()
            self.cfg.tokens_txt = w_txt.text()
            self.cfg.tokens_csv = w_csv.text()
            try:
                self.save_config()
            except Exception:
                pass
            dlg.accept()

        apply_btn.clicked.connect(apply)
        close_btn.clicked.connect(dlg.reject)

        dlg.exec()
    def start_auto(self):
        if self.worker and self.worker.isRunning():
            show_message(self, "Уже работает", "Сначала остановите текущий процесс.")
            return

        chat = self.auto_page.chat.text().strip() or BOTFATHER_USERNAME_DEFAULT
        raw = self.auto_page.names.text().strip()
        names = [n.strip() for n in raw.split("/") if n.strip()]
        if not names:
            show_message(self, "Ошибка", "Введите имена через '/'.")
            return
        if not self.image_path:
            show_message(self, "Ошибка", "Выберите картинку (обязательно).")
            return
        hamster = self.auto_page.hamster.currentText().strip() or "None"
        self.log(f"[INFO] Авто-режим. Хомяк: {hamster}")

        self.worker = Worker("auto", chat, names, hamster, self.image_path, self.cfg, self.bridge, self.bot_overrides, self.account_status)
        self.worker.log.connect(self.log)
        self.worker.progress.connect(self.log)
        self.worker.finished_ok.connect(self._on_auto_finished)
        self.worker.start()

    def start_manual(self):
        show_message(self, "Ручной режим", "Ручной режим в этой версии использует авто-логику. Рекомендуется авто-режим.")
        # Simplified: manual not fully implemented in this single-file build.

    def open_bot_customization(self):
        raw = self.auto_page.names.text().strip()
        names = [n.strip() for n in raw.split("/") if n.strip()]
        if not names:
            show_message(self, "Ошибка", "Введите имена через '/'.")
            return
        name, ok = QInputDialog.getItem(self, "Выберите бота", "Имя бота:", names, 0, False)
        if not ok or not name:
            return
        self._open_bot_customization_dialog(name)

    def _open_bot_customization_dialog(self, base_name: str):
        override = self.bot_overrides.get(base_name, {})
        dlg = StyledDialog(self, f"Кастомизация: {base_name}")
        dlg.resize(760, 420)

        form = QFormLayout()
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(14)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        w_prefix = QLineEdit(override.get("name_prefix", self.cfg.name_prefix)); w_prefix.setObjectName("Input")
        w_suffix = QLineEdit(override.get("name_suffix", self.cfg.name_suffix)); w_suffix.setObjectName("Input")
        w_user_suffix = QLineEdit(override.get("username_suffix", self.cfg.username_suffix)); w_user_suffix.setObjectName("Input")
        w_sep = QLineEdit(override.get("numbered_separator", self.cfg.numbered_separator)); w_sep.setObjectName("Input")
        w_num = QLineEdit(override.get("numbered_suffix", self.cfg.numbered_suffix)); w_num.setObjectName("Input")
        w_max = QSpinBox(); w_max.setRange(1, 50); w_max.setValue(int(override.get("max_number_attempts", self.cfg.max_number_attempts))); w_max.setObjectName("Input")
        w_sanitize = QCheckBox("Санитизировать username")
        w_sanitize.setChecked(bool(override.get("sanitize_username", self.cfg.sanitize_username)))

        form.addRow("Префикс имени:", w_prefix)
        form.addRow("Суффикс имени:", w_suffix)
        form.addRow("Окончание username:", w_user_suffix)
        form.addRow("Разделитель перед номером:", w_sep)
        form.addRow("Текст после номера:", w_num)
        form.addRow("Попыток номеров:", w_max)
        form.addRow("", w_sanitize)

        btn_row = QHBoxLayout()
        apply_btn = QPushButton("Применить"); apply_btn.setObjectName("PrimaryBtn")
        close_btn = QPushButton("Закрыть"); close_btn.setObjectName("SecondaryBtn")
        btn_row.addWidget(apply_btn); btn_row.addWidget(close_btn); btn_row.addStretch(1)

        wrap = QVBoxLayout()
        wrap.addLayout(form)
        wrap.addSpacing(8)
        wrap.addLayout(btn_row)
        dlg.set_body_layout(wrap)

        def apply():
            self.bot_overrides[base_name] = {
                "name_prefix": w_prefix.text(),
                "name_suffix": w_suffix.text(),
                "username_suffix": w_user_suffix.text(),
                "numbered_separator": w_sep.text(),
                "numbered_suffix": w_num.text(),
                "max_number_attempts": int(w_max.value()),
                "sanitize_username": w_sanitize.isChecked(),
            }
            show_message(self, "Готово", f"Кастомизация сохранена для: {base_name}")
            dlg.accept()

        apply_btn.clicked.connect(apply)
        close_btn.clicked.connect(dlg.reject)
        dlg.exec()


    def _heartbeat(self):
        try:
            w = getattr(self, "worker", None)
            # If worker exists and thread running, and no logs for 12s -> add heartbeat
            if w is not None and getattr(w, "_running", False):
                if time.time() - getattr(self, "_last_log_ts", 0) >= 12:
                    self.on_log("[INFO] Работаю... (heartbeat)")
        except Exception:
            pass

def main():
    app = QApplication(sys.argv)
    w = BotFactoryApp()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
