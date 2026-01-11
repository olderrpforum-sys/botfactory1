# BotFactory — single-file app.py (PyQt6 + Telethon)
# Requires: Python 3.11, pip install -r requirements.txt
import os
import time, sys, re, csv, json, asyncio, time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, List, Dict, Tuple

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QTimer, QSize, QPoint
from PyQt6.QtGui import QColor, QPainter, QPixmap, QIcon
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
    QMessageBox,
    QStackedWidget,
    QComboBox,
    QSpinBox,
    QCheckBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QDialog,
    QFormLayout,
    QGraphicsDropShadowEffect,
    QInputDialog
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
        accs.append({
            "phone": phone.strip(),
            "password": None if pwd.strip().upper() == "UNKNOWN" else pwd.strip(),
            "api_id": int(api_id.strip()),
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
    per_account_limit: int = 2
    freeze_threshold_seconds: int = 350
    force_setuserpic_delay1: float = 1.0
    force_setuserpic_delay2: float = 1.0

    def tokens_txt_path(self) -> Path:
        p = Path(self.tokens_txt)
        return p if p.is_absolute() else BASE_DIR / p

    def tokens_csv_path(self) -> Path:
        p = Path(self.tokens_csv)
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
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(10)

        self.title_lbl = QLabel(title)
        self.title_lbl.setObjectName("TitleBarText")
        lay.addWidget(self.title_lbl)
        lay.addStretch(1)

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

        lay.addWidget(self.btn_min)
        lay.addWidget(self.btn_max)
        lay.addWidget(self.btn_close)

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

class LogBox(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("LogBox")
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
        self.text.setPlaceholderText("Логи появятся здесь…")

        lay.addWidget(self.text)

    def append(self, s: str):
        # Do not resize the UI: log area is scrollable and has fixed max height
        self.text.appendPlainText(s)
        sb = self.text.verticalScrollBar()
        sb.setValue(sb.maximum())

class Worker(QThread):

    log = pyqtSignal(str)
    progress = pyqtSignal(str)
    finished_ok = pyqtSignal()

    def __init__(self, mode: str, chat: str, names: List[str], hamster: str,
                 image_path: str, cfg: AutoConfig, bridge: PromptBridge):
        super().__init__()
        self.mode = mode
        self.chat = chat
        self.names = names
        self.hamster = hamster
        self.image_path = image_path
        self.cfg = cfg
        self.bridge = bridge
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
        return f"{self.cfg.name_prefix}{base}{self.cfg.name_suffix}"

    def _build_username_candidates(self, base: str) -> List[str]:
        b = sanitize_base(base) if self.cfg.sanitize_username else base
        candidates = [f"{b}{self.cfg.username_suffix}"]
        for n in range(1, self.cfg.max_number_attempts + 1):
            candidates.append(f"{b}{self.cfg.numbered_separator}{n}{self.cfg.numbered_suffix}")
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

    async def _create_one_bot(self, client: TelegramClient, base_name: str) -> Optional[Tuple[str, str]]:
        peer = self.chat

        # /newbot with retry
        ok, resp = await self._send_rate_aware(client, peer, "/newbot")
        if not ok:
            sec = extract_try_again_seconds(resp) or 0
            if sec > self.cfg.freeze_threshold_seconds:
                return None
            await self._wait_rate(sec + 1)
            await client(SendMessageRequest(peer, "/newbot"))
            await asyncio.sleep(0.8)

        # name
        await client(SendMessageRequest(peer, self._build_bot_name(base_name)))
        await asyncio.sleep(0.8)

        # username tries
        for uname in self._build_username_candidates(base_name):
            if self.stop_requested:
                return None
            await client(SendMessageRequest(peer, uname))
            await asyncio.sleep(0.9)

            msgs = await client.get_messages(peer, limit=3)
            joined = "\n".join([m.text or "" for m in msgs])

            sec = extract_try_again_seconds(joined)
            if sec:
                if sec > self.cfg.freeze_threshold_seconds:
                    return None
                await self._wait_rate(sec + 1)
                continue

            if "Sorry, this username is invalid." in joined or "invalid" in joined.lower():
                continue

            if ("Done!" in joined) or ("Congratulations" in joined) or ("You will find it at" in joined):
                token = extract_token(joined) or ""
                # Иногда токен приходит отдельным сообщением/с задержкой — подождём и поищем принудительно
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

        ok, resp = await self._send_rate_aware(client, peer, "/setuserpic")
        if not ok:
            sec = extract_try_again_seconds(resp) or 0
            if sec > self.cfg.freeze_threshold_seconds:
                return
            await self._wait_rate(sec + 1)
            await client(SendMessageRequest(peer, "/setuserpic"))
            await asyncio.sleep(0.8)

        await asyncio.sleep(self.cfg.force_setuserpic_delay1)
        await client(SendMessageRequest(peer, f"@{username}"))
        await asyncio.sleep(self.cfg.force_setuserpic_delay2)
        await client.send_file(peer, self.image_path)

    def _write_token(self, username: str, token: str, hamster: str):
        ensure_file(self.cfg.tokens_txt_path())
        ensure_file(self.cfg.tokens_csv_path())
        with open(self.cfg.tokens_txt_path(), "a", encoding="utf-8") as f:
            f.write(f"{token}\n")
        exists = self.cfg.tokens_csv_path().exists() and self.cfg.tokens_csv_path().stat().st_size > 0
        with open(self.cfg.tokens_csv_path(), "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if not exists:
                w.writerow(["username", "token", "hamster", "ts"])
            w.writerow([username, token, hamster, int(time.time())])

    async def _run_async(self):
        accs = parse_accounts(ACCOUNTS_FILE)
        if not accs:
            self.log.emit("[ERROR] accounts_tg.txt не найден или пуст.")
            return

        names_queue = list(self.names)
        frozen = load_json(FROZEN_FILE, {})
        per_acc = {a["phone"]: 0 for a in accs}

        def is_frozen(phone: str) -> bool:
            until = safe_int(str(frozen.get(phone, 0)), 0)
            return until > int(time.time())

        self.log.emit(f"[INFO] Аккаунтов: {len(accs)} | Имен: {len(names_queue)} | Лимит/акк: {self.cfg.per_account_limit} (1 запуск = 1 круг)")

        acc_index = 0
        while names_queue and not self.stop_requested:
            acc = accs[acc_index % len(accs)]
            acc_index += 1

            if per_acc[acc["phone"]] >= self.cfg.per_account_limit:
                continue
            if is_frozen(acc["phone"]):
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
                        self.log.emit(f"[FREEZE] {acc['phone']} заморожен на {sec}s. Переходим к следующему аккаунту, бот НЕ потерян.")
                    else:
                        self.log.emit("[WARN] Не удалось создать бота — пробуем другим аккаунтом.")
                    continue

                username, token = created
                self.log.emit(f"[OK] Создан @{username}")
                if token:
                    self._write_token(username, token, self.hamster)
                    self.log.emit("[OK] Токен сохранён.")
                else:
                    self.log.emit("[WARN] Токен не найден (редко).")

                await self._set_userpic(client, username)
                per_acc[acc["phone"]] += 1

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
            except Exception as e:
                names_queue.insert(0, base)
                self.log.emit(f"[ERROR] {e}")
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass

        self.log.emit("[OK] Готово.")

class ManualPage(QWidget):
    def __init__(self, ui):
        super().__init__()
        self.ui = ui
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0)

        card = QFrame(); card.setObjectName("Card")
        c = QVBoxLayout(card); c.setContentsMargins(18,18,18,18); c.setSpacing(12)

        title = QLabel("Ручное создание"); title.setObjectName("PageTitle")
        c.addWidget(title)

        self.chat = QLineEdit(BOTFATHER_USERNAME_DEFAULT); self.chat.setObjectName("Input")
        self.bot_name = QLineEdit(""); self.bot_name.setObjectName("Input")
        self.bot_username = QLineEdit(""); self.bot_username.setObjectName("Input")

        self.bot_name.setPlaceholderText("Имя бота (можно emoji)")
        self.bot_username.setPlaceholderText("Username (пример: mybot_bot)")

        row = QHBoxLayout()
        self.pick_img = QPushButton("Выбрать картинку"); self.pick_img.setObjectName("PrimaryBtn")
        self.pick_img.clicked.connect(self.ui.pick_image)
        row.addWidget(self.pick_img); row.addStretch(1)

        btn_row = QHBoxLayout()
        self.start = QPushButton("Запуск (Ручной режим)"); self.start.setObjectName("PrimaryBtn")
        self.stop = QPushButton("Стоп"); self.stop.setObjectName("SecondaryBtn")
        self.start.clicked.connect(self.ui.start_manual)
        self.stop.clicked.connect(self.ui.stop_worker)
        btn_row.addWidget(self.start); btn_row.addWidget(self.stop); btn_row.addStretch(1)

        c.addWidget(QLabel("Чат:")); c.addWidget(self.chat)
        c.addWidget(QLabel("Имя:")); c.addWidget(self.bot_name)
        c.addWidget(QLabel("Username:")); c.addWidget(self.bot_username)
        c.addLayout(row)
        c.addLayout(btn_row)

        lay.addWidget(card)
        lay.addWidget(self.ui.logbox, 1)

class AutoPage(QWidget):
    def __init__(self, ui):
        super().__init__()
        self.ui = ui
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0)

        card = QFrame(); card.setObjectName("Card")
        c = QVBoxLayout(card); c.setContentsMargins(18,18,18,18); c.setSpacing(12)

        title = QLabel("Автоматическое создание"); title.setObjectName("PageTitle")
        c.addWidget(title)

        self.chat = QLineEdit(BOTFATHER_USERNAME_DEFAULT); self.chat.setObjectName("Input")
        self.names = QLineEdit(""); self.names.setObjectName("Input")
        self.names.setPlaceholderText("name/name2/name3 (без пробелов желательно)")

        self.hamster = QComboBox(); self.hamster.setObjectName("Input")
        self.hamster.addItem("None")

        row = QHBoxLayout()
        self.pick_img = QPushButton("Выбрать картинку (обязательно)"); self.pick_img.setObjectName("PrimaryBtn")
        self.pick_img.clicked.connect(self.ui.pick_image)
        row.addWidget(self.pick_img); row.addStretch(1)

        hint = QLabel("Лимит: строго 2 бота на аккаунт за 1 запуск (1 запуск = 1 круг)."); hint.setObjectName("Hint")

        btn_row = QHBoxLayout()
        self.custom = QPushButton("Кастомизация"); self.custom.setObjectName("SecondaryBtn")
        self.start = QPushButton("Запуск (Авто режим)"); self.start.setObjectName("PrimaryBtn")
        self.stop = QPushButton("Стоп"); self.stop.setObjectName("SecondaryBtn")

        self.custom.clicked.connect(self.ui.open_customization)
        self.start.clicked.connect(self.ui.start_auto)
        self.stop.clicked.connect(self.ui.stop_worker)

        btn_row.addWidget(self.custom); btn_row.addWidget(self.start); btn_row.addWidget(self.stop); btn_row.addStretch(1)

        c.addWidget(QLabel("Чат:")); c.addWidget(self.chat)
        c.addWidget(QLabel("Имена:")); c.addWidget(self.names)
        c.addWidget(QLabel("Хомяк:")); c.addWidget(self.hamster)
        c.addLayout(row)
        c.addWidget(hint)
        c.addLayout(btn_row)

        lay.addWidget(card)
        lay.addWidget(self.ui.logbox, 1)

class StatsPage(QWidget):
    def __init__(self, ui):
        super().__init__()
        self.ui = ui
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0)

        card = QFrame(); card.setObjectName("Card")
        c = QVBoxLayout(card); c.setContentsMargins(18,18,18,18); c.setSpacing(12)

        title = QLabel("Статистика"); title.setObjectName("PageTitle")
        c.addWidget(title)

        row = QHBoxLayout()
        self.name = QLineEdit(""); self.name.setObjectName("Input"); self.name.setPlaceholderText("Название хомяка")
        self.percent = QSpinBox(); self.percent.setRange(0,100); self.percent.setValue(50); self.percent.setObjectName("Input")
        add = QPushButton("Добавить хомяка"); add.setObjectName("PrimaryBtn")
        add.clicked.connect(self.add_hamster)
        row.addWidget(self.name, 2)
        row.addWidget(QLabel("Процент:"))
        row.addWidget(self.percent)
        row.addWidget(add)
        c.addLayout(row)

        self.table = QTableWidget(0, 3)
        self.table.setObjectName("StatsTable")

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

    def add_hamster(self):
        name = self.name.text().strip()
        if not name:
            QMessageBox.warning(self, "Ошибка", "Введите название хомяка.")
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
        self.ui.hamsters.pop(name, None)
        self.ui.save_hamsters()
        self.refresh_table()
        self.ui.auto_page_update_hamsters()

class BotFactoryApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.resize(1220, 740)

        self.cfg = AutoConfig(**load_json(CONFIG_FILE, asdict(AutoConfig())))
        # Ensure tokens output files exist on startup
        ensure_file(self.cfg.tokens_txt_path())
        ensure_file(self.cfg.tokens_csv_path())
        self.hamsters = load_json(HAMSTERS_FILE, {})
        if not isinstance(self.hamsters, dict):
            self.hamsters = {}
        self.image_path = ""
        self.worker: Optional[Worker] = None
        self.bridge = PromptBridge()

        root = QWidget(); self.setCentralWidget(root)
        root_lay = QVBoxLayout(root); root_lay.setContentsMargins(0,0,0,0); root_lay.setSpacing(0)

        self.titlebar = PremiumTitleBar(self, "")
        root_lay.addWidget(self.titlebar)

        body = QHBoxLayout(); body.setContentsMargins(18,18,18,18); body.setSpacing(16)
        root_lay.addLayout(body)

        sidebar = QFrame(); sidebar.setObjectName("Sidebar")
        side = QVBoxLayout(sidebar); side.setContentsMargins(18,18,18,18); side.setSpacing(10)

        brand = QLabel(APP_NAME); brand.setObjectName("BrandTitle")
        by = QLabel(BYLINE); by.setObjectName("BrandBy")
        side.addWidget(brand); side.addWidget(by); side.addSpacing(10)

        self.btn_manual = QPushButton("Ручное создание"); self.btn_manual.setObjectName("NavBtn")
        self.btn_auto = QPushButton("Автоматическое создание"); self.btn_auto.setObjectName("NavBtn")
        self.btn_stats = QPushButton("Статистика"); self.btn_stats.setObjectName("NavBtn")

        side.addWidget(self.btn_manual); side.addWidget(self.btn_auto); side.addWidget(self.btn_stats)
        side.addStretch(1)
        foot = QLabel("Выход: tokens.txt • tokens.csv • sessions/"); foot.setObjectName("Footer")
        side.addWidget(foot)
        body.addWidget(sidebar, 1)

        self.logbox = LogBox()
        self.stack = QStackedWidget(); self.stack.setObjectName("Stack")

        self.manual_page = ManualPage(self)
        self.auto_page = AutoPage(self)
        self.stats_page = StatsPage(self)

        self.stack.addWidget(self.manual_page)
        self.stack.addWidget(self.auto_page)
        self.stack.addWidget(self.stats_page)

        content_wrap = QFrame(); content_wrap.setObjectName("ContentWrap")
        cw = QVBoxLayout(content_wrap); cw.setContentsMargins(0,0,0,0)
        cw.addWidget(self.stack, 1)
        body.addWidget(content_wrap, 3)

        self.btn_manual.clicked.connect(lambda: self._nav(0))
        self.btn_auto.clicked.connect(lambda: self._nav(1))
        self.btn_stats.clicked.connect(lambda: self._nav(2))
        self._nav(1)

        self.bridge.request_code.connect(self._ask_code)
        self.bridge.request_password.connect(self._ask_password)

        self.setStyleSheet(self._style())
        QTimer.singleShot(0, lambda: center_on_screen(self))
        self.auto_page_update_hamsters()

    def _style(self) -> str:
        return """
        * { font-family: Arial; }
        QLabel { color: rgba(230,237,243,0.92); font-weight: 900; margin-bottom: 2px; }
        QCheckBox { color: rgba(230,237,243,0.92); font-weight: 900; spacing: 10px; }
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

        QMainWindow { background: #070b16; }
        #PremiumTitleBar { background: rgba(8, 12, 22, 0.96); border-bottom: 1px solid rgba(255,255,255,0.06); }
        #TitleBarText { color: rgba(230,237,243,0.90); font-weight: 900; font-size: 14px; }
        QPushButton#WinBtn, QPushButton#WinClose {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 10px;
        }
        QPushButton#WinBtn:hover { background: rgba(0, 200, 255, 0.12); border-color: rgba(0,200,255,0.22); }
        QPushButton#WinClose:hover { background: rgba(255, 83, 112, 0.18); border-color: rgba(255,83,112,0.24); }

        #Sidebar {
            background: rgba(8, 12, 22, 0.90);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 22px;
        }
        #BrandTitle { color: rgba(230,237,243,0.96); font-weight: 1000; font-size: 26px; }
        #BrandBy { color: rgba(230,237,243,0.55); font-weight: 900; font-size: 12px; margin-top: -4px; }
        #Footer { color: rgba(230,237,243,0.70); font-size: 11px; font-weight: 800; }

        #ContentWrap {
            background: rgba(8, 12, 22, 0.65);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 22px;
        }

        #Card {
            background: rgba(8, 12, 22, 0.80);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 22px;
        }
        #PageTitle { color: rgba(230,237,243,0.96); font-size: 22px; font-weight: 1000; }
        #Hint { color: rgba(230,237,243,0.70); font-size: 12px; font-weight: 800; }

        #Input {
            min-height: 36px;
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 16px;
            padding: 10px 14px;
            color: rgba(230,237,243,0.95);
            font-weight: 800;
        }

        #NavBtn {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 16px;
            padding: 12px 12px;
            color: rgba(230,237,243,0.92);
            font-weight: 900;
            text-align: left;
        }
        #NavBtn:hover { background: rgba(255,255,255,0.08); }
        #NavBtn[active="true"] {
            background: rgba(120, 60, 255, 0.18);
            border: 1px solid rgba(120, 60, 255, 0.22);
        }

        #PrimaryBtn {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(50,120,255,0.95), stop:0.5 rgba(140,70,255,0.95), stop:1 rgba(0,200,255,0.95));
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 18px;
            padding: 10px 14px;
            color: rgba(255,255,255,0.98);
            font-weight: 1000;
        }
        #PrimaryBtn:hover { border-color: rgba(255,255,255,0.18); }

        #SecondaryBtn {
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 18px;
            padding: 10px 14px;
            color: rgba(230,237,243,0.95);
            font-weight: 1000;
        }
        #SecondaryBtn:hover { background: rgba(255,255,255,0.10); }

        #LogBox {
            background: rgba(8, 12, 22, 0.55);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 22px;
        }
        #LogText { color: rgba(230,237,243,0.86); font-weight: 800; font-size: 12px; }

        #StatsTable {
            background: rgba(8, 12, 22, 0.35);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 18px;
            color: rgba(230,237,243,0.90);
            gridline-color: rgba(255,255,255,0.06);
        }
        QHeaderView::section {
            background: rgba(8, 12, 22, 0.80);
            color: rgba(230,237,243,0.80);
            border: none;
            padding: 8px;
            font-weight: 900;
        }

        QDialog#PremiumDialog { background: transparent; }
        #PremiumDialogCard {
            background: rgba(8, 12, 22, 0.98);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 22px;
        }
        #PremiumDialogTitle { color: rgba(230,237,243,0.95); font-weight: 1000; font-size: 14px; }
        

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
        btns = [self.btn_manual, self.btn_auto, self.btn_stats]
        for i, b in enumerate(btns):
            b.setProperty("active", "true" if i == idx else "false")
            b.style().unpolish(b)
            b.style().polish(b)

    def save_config(self):
        save_json(CONFIG_FILE, asdict(self.cfg))

    def save_hamsters(self):
        save_json(HAMSTERS_FILE, self.hamsters)

    def auto_page_update_hamsters(self):
        self.auto_page.hamster.clear()
        self.auto_page.hamster.addItem("None")
        for name in sorted(self.hamsters.keys()):
            self.auto_page.hamster.addItem(name)

    def log(self, s: str):
        self.logbox.append(s)

    def pick_image(self):
        p, _ = QFileDialog.getOpenFileName(self, "Выбрать картинку", str(BASE_DIR), "Images (*.png *.jpg *.jpeg *.webp)")
        if p:
            self.image_path = p
            self.log(f"[OK] Картинка: {p}")

    def _ask_code(self, phone: str):
        code, ok = QInputDialog.getText(self, "Код авторизации", f"Введите код для {phone}:")
        self.bridge.set_code(code if ok else "")

    def _ask_password(self, phone: str):
        pwd, ok = QInputDialog.getText(self, "Пароль 2FA", f"Введите пароль 2FA для {phone}:")
        self.bridge.set_password(pwd if ok else "")

    def stop_worker(self):
        if self.worker:
            self.worker.stop()
            self.log("[INFO] Stop запрошен.")


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

        form.addRow("Префикс (будет ПЕРЕД именем):", w_prefix)
        form.addRow("Суффикс (будет ПОСЛЕ имени):", w_suffix)

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
            QMessageBox.warning(self, "Уже работает", "Сначала остановите текущий процесс.")
            return

        chat = self.auto_page.chat.text().strip() or BOTFATHER_USERNAME_DEFAULT
        raw = self.auto_page.names.text().strip()
        names = [n.strip() for n in raw.split("/") if n.strip()]
        if not names:
            QMessageBox.warning(self, "Ошибка", "Введите имена через '/'.")
            return
        if not self.image_path:
            QMessageBox.warning(self, "Ошибка", "Выберите картинку (обязательно).")
            return
        hamster = self.auto_page.hamster.currentText().strip() or "None"
        self.log(f"[INFO] Авто-режим. Хомяк: {hamster}")

        self.worker = Worker("auto", chat, names, hamster, self.image_path, self.cfg, self.bridge)
        self.worker.log.connect(self.log)
        self.worker.progress.connect(self.log)
        self.worker.start()

    def start_manual(self):
        QMessageBox.information(self, "Ручной режим", "Ручной режим в этой версии использует авто-логику. Рекомендуется авто-режим.")
        # Simplified: manual not fully implemented in this single-file build.


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
