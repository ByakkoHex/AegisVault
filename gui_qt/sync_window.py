"""
sync_window.py — Okno konfiguracji i statusu synchronizacji (PyQt6)
====================================================================
"""

import threading

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal

from utils.sync_client import SyncClient
from utils.prefs_manager import PrefsManager


def _accent() -> str:
    return PrefsManager().get_accent()


def _accent_hover() -> str:
    return PrefsManager().get_accent_hover()


def _is_dark() -> bool:
    from gui_qt.style import current_dark
    try:
        return current_dark()
    except Exception:
        return True


class SyncWindow(QDialog):
    _status_sig  = pyqtSignal(bool)          # server reachable?
    _auth_sig    = pyqtSignal(str, bool)     # message, success
    _sync_sig    = pyqtSignal(str, bool)     # message, success

    def __init__(
        self,
        parent: QWidget,
        db,
        crypto,
        user,
        sync_client: SyncClient,
        on_refresh=None,
    ):
        super().__init__(parent)
        self.db         = db
        self.crypto     = crypto
        self.user       = user
        self.sync       = sync_client
        self.on_refresh = on_refresh

        self.setWindowTitle("Synchronizacja")
        self.setFixedSize(460, 680)
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)

        self._status_sig.connect(self._on_status)
        self._auth_sig.connect(self._on_auth)
        self._sync_sig.connect(self._on_sync_result)

        self._build_ui()
        self._check_status()

        from PyQt6.QtCore import QPropertyAnimation, QEasingCurve
        self.setWindowOpacity(0.0)
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(150)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._fade_anim.start()

    # ──────────────────────────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────────────────────────

    def _build_ui(self):
        dark  = _is_dark()
        bg    = "#1a1a1a" if dark else "#f5f5f5"
        card  = "#1e1e1e" if dark else "#fafafa"
        fg    = "#e8e8e8" if dark else "#1a1a1a"
        sub   = "#888888"
        brd   = "#2e2e2e" if dark else "#d0d0d0"
        acc   = _accent()
        acc_h = _accent_hover()

        self.setStyleSheet(f"""
            QDialog {{
                background: {bg};
                border: 1px solid {brd};
                border-radius: 12px;
            }}
            QLabel {{ color: {fg}; background: transparent; }}
            QLineEdit {{
                background: {card};
                color: {fg};
                border: 1px solid {"#3a3a3a" if dark else "#cccccc"};
                border-radius: 10px;
                padding: 8px 12px;
                font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {acc}; }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 20)
        root.setSpacing(0)

        # ── Nagłówek ────────────────────────────────────────────
        hdr = QFrame()
        hdr.setFixedHeight(62)
        hdr.setStyleSheet(f"""
            QFrame {{
                background: {"#1f2d44" if dark else "#ddeeff"};
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }}
        """)
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(20, 0, 20, 0)

        title_lbl = QLabel("🔄  Synchronizacja")
        title_lbl.setStyleSheet(f"color: {fg}; font-size: 19px; font-weight: bold;")
        hdr_lay.addWidget(title_lbl, 1)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {sub};
                border: none;
                font-size: 13px;
                border-radius: 14px;
            }}
            QPushButton:hover {{ background: {"#333" if dark else "#ddd"}; }}
        """)
        close_btn.clicked.connect(self.reject)
        hdr_lay.addWidget(close_btn)
        root.addWidget(hdr)

        # Gradient separator
        from gui_qt.gradient import AnimatedGradientWidget
        sep = AnimatedGradientWidget(
            self, accent=acc, base=bg, anim_mode="slide", fps=20, period_ms=6000
        )
        sep.setFixedHeight(2)
        root.addWidget(sep)

        # Podtytuł
        sub_lbl = QLabel("Synchronizuj hasła między urządzeniami przez lokalny serwer.")
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_lbl.setStyleSheet(f"color: {sub}; font-size: 12px; margin: 12px 0 8px 0;")
        root.addWidget(sub_lbl)

        # ── Status serwera ──────────────────────────────────────
        root.addLayout(self._card_widget(
            self._build_server_status(card, fg, sub, brd, acc),
            bg, brd
        ))
        root.addSpacing(8)

        # ── Logowanie ───────────────────────────────────────────
        root.addLayout(self._card_widget(
            self._build_login(card, fg, sub, brd, acc, acc_h, dark),
            bg, brd
        ))
        root.addSpacing(8)

        # ── Sync przyciski ──────────────────────────────────────
        root.addLayout(self._card_widget(
            self._build_sync_buttons(card, fg, sub, brd, acc, acc_h, dark),
            bg, brd
        ))
        root.addStretch()

        # ── Zamknij ─────────────────────────────────────────────
        close_row = QHBoxLayout()
        close_row.setContentsMargins(20, 0, 20, 0)
        close_main = QPushButton("Zamknij")
        close_main.setFixedHeight(40)
        close_main.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {fg};
                border: 1px solid {"#3a3a3a" if dark else "#cccccc"};
                border-radius: 10px;
                font-size: 13px;
            }}
            QPushButton:hover {{ background: {"#2a2a2a" if dark else "#e8e8e8"}; }}
        """)
        close_main.clicked.connect(self.reject)
        close_row.addWidget(close_main)
        root.addLayout(close_row)

    def _card_widget(self, inner: QWidget, bg: str, brd: str) -> QHBoxLayout:
        """Opakowuje widget w card frame z marginesem."""
        card_wrap = QFrame()
        card_wrap.setStyleSheet(f"""
            QFrame {{
                background: {"#1e1e1e" if _is_dark() else "#fafafa"};
                border: 1px solid {brd};
                border-radius: 12px;
            }}
        """)
        lay = QVBoxLayout(card_wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(inner)
        row = QHBoxLayout()
        row.setContentsMargins(20, 0, 20, 0)
        row.addWidget(card_wrap)
        return row

    def _build_server_status(self, card, fg, sub, brd, acc) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(4)

        row = QHBoxLayout()
        lbl = QLabel("Status serwera:")
        lbl.setStyleSheet(f"color: {fg}; font-size: 13px;")
        row.addWidget(lbl)
        row.addStretch()

        self._status_lbl = QLabel("⏳ Sprawdzanie...")
        self._status_lbl.setStyleSheet(f"color: {sub}; font-size: 13px; font-weight: bold;")
        row.addWidget(self._status_lbl)
        lay.addLayout(row)

        addr_lbl = QLabel(f"Adres: {self.sync.server_url}")
        addr_lbl.setStyleSheet(f"color: {sub}; font-size: 11px;")
        lay.addWidget(addr_lbl)
        return w

    def _build_login(self, card, fg, sub, brd, acc, acc_h, dark) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)

        title = QLabel("🔐 Konto synchronizacji")
        title.setStyleSheet(f"color: {fg}; font-size: 14px; font-weight: bold;")
        lay.addWidget(title)

        hint = QLabel("Osobne konto na serwerze sync (może być takie samo jak lokalne).")
        hint.setStyleSheet(f"color: {sub}; font-size: 11px;")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        lbl_u = QLabel("Login")
        lbl_u.setStyleSheet(f"color: {fg}; font-size: 12px;")
        lay.addWidget(lbl_u)

        self._entry_user = QLineEdit()
        self._entry_user.setPlaceholderText("Nazwa użytkownika...")
        self._entry_user.setFixedHeight(38)
        self._entry_user.setText(self.user.username)
        lay.addWidget(self._entry_user)

        lbl_p = QLabel("Hasło do serwera")
        lbl_p.setStyleSheet(f"color: {fg}; font-size: 12px; margin-top: 4px;")
        lay.addWidget(lbl_p)

        self._entry_pass = QLineEdit()
        self._entry_pass.setPlaceholderText("Hasło...")
        self._entry_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self._entry_pass.setFixedHeight(38)
        lay.addWidget(self._entry_pass)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        reg_btn = QPushButton("Zarejestruj na serwerze")
        reg_btn.setFixedHeight(36)
        reg_btn_bg  = "#2a2a2a" if dark else "#f0f0f0"
        reg_btn_fg  = "#cccccc" if dark else "#333333"
        reg_btn_hov = "#383838" if dark else "#e0e0e0"
        reg_btn.setStyleSheet(f"""
            QPushButton {{
                background: {reg_btn_bg};
                color: {reg_btn_fg};
                border: 1px solid {"#3a3a3a" if dark else "#cccccc"};
                border-radius: 10px;
                font-size: 12px;
            }}
            QPushButton:hover {{ background: {reg_btn_hov}; }}
        """)
        reg_btn.clicked.connect(self._register_account)
        btn_row.addWidget(reg_btn, 1)

        login_btn = QPushButton("Zaloguj")
        login_btn.setFixedHeight(36)
        login_btn.setStyleSheet(f"""
            QPushButton {{
                background: {acc};
                color: #ffffff;
                border: none;
                border-radius: 10px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {acc_h}; }}
        """)
        login_btn.clicked.connect(self._login)
        btn_row.addWidget(login_btn, 1)
        lay.addLayout(btn_row)

        self._auth_lbl = QLabel("")
        self._auth_lbl.setStyleSheet(f"color: {sub}; font-size: 11px;")
        self._auth_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._auth_lbl)
        return w

    def _build_sync_buttons(self, card, fg, sub, brd, acc, acc_h, dark) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        title = QLabel("🔄 Synchronizacja danych")
        title.setStyleSheet(f"color: {fg}; font-size: 14px; font-weight: bold;")
        lay.addWidget(title)

        sync_btn_row = QHBoxLayout()
        sync_btn_row.setSpacing(8)

        push_bg  = "#1a3a5c" if dark else "#ddeeff"
        push_fg  = "#7ab8f5" if dark else acc
        push_hov = "#1e4a70" if dark else "#cce0ff"

        push_btn = QPushButton("📤 Wyślij na serwer")
        push_btn.setFixedHeight(40)
        push_btn.setStyleSheet(f"""
            QPushButton {{
                background: {push_bg};
                color: {push_fg};
                border: none;
                border-radius: 10px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {push_hov}; }}
        """)
        push_btn.clicked.connect(self._push)
        sync_btn_row.addWidget(push_btn, 1)

        pull_btn = QPushButton("📥 Pobierz z serwera")
        pull_btn.setFixedHeight(40)
        pull_btn.setStyleSheet(f"""
            QPushButton {{
                background: {push_bg};
                color: {push_fg};
                border: none;
                border-radius: 10px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {push_hov}; }}
        """)
        pull_btn.clicked.connect(self._pull)
        sync_btn_row.addWidget(pull_btn, 1)

        lay.addLayout(sync_btn_row)

        self._sync_lbl = QLabel("")
        self._sync_lbl.setStyleSheet(f"color: {sub}; font-size: 11px;")
        self._sync_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._sync_lbl)
        return w

    # ──────────────────────────────────────────────────────────────────
    # Slots
    # ──────────────────────────────────────────────────────────────────

    def _on_status(self, connected: bool) -> None:
        if connected:
            self._status_lbl.setText("🟢 Połączony")
            self._status_lbl.setStyleSheet("color: #38a169; font-size: 13px; font-weight: bold;")
        else:
            self._status_lbl.setText("🔴 Niedostępny")
            self._status_lbl.setStyleSheet("color: #e53e3e; font-size: 13px; font-weight: bold;")

    def _on_auth(self, msg: str, success: bool) -> None:
        color = "#38a169" if success else "#e53e3e"
        self._auth_lbl.setStyleSheet(f"color: {color}; font-size: 11px;")
        self._auth_lbl.setText(msg)

    def _on_sync_result(self, msg: str, success: bool) -> None:
        color = "#38a169" if success else "#e53e3e"
        self._sync_lbl.setStyleSheet(f"color: {color}; font-size: 11px;")
        self._sync_lbl.setText(msg)

    # ──────────────────────────────────────────────────────────────────
    # Actions (threaded)
    # ──────────────────────────────────────────────────────────────────

    def _check_status(self) -> None:
        def _run():
            try:
                connected = self.sync.is_connected()
            except Exception:
                import logging
                logging.getLogger("aegisvault").exception("Błąd sprawdzania statusu synchronizacji")
                connected = False
            self._status_sig.emit(connected)
        threading.Thread(target=_run, daemon=True).start()

    def _register_account(self) -> None:
        username = self._entry_user.text().strip()
        password = self._entry_pass.text()
        if not username or not password:
            self._on_auth("Wypełnij oba pola!", False)
            return
        try:
            self.sync.register(username, password)
            self._on_auth("✅ Konto utworzone! Możesz się zalogować.", True)
        except Exception as e:
            self._on_auth(f"❌ {e}", False)

    def _login(self) -> None:
        username = self._entry_user.text().strip()
        password = self._entry_pass.text()
        if not username or not password:
            self._on_auth("Wypełnij oba pola!", False)
            return
        try:
            success = self.sync.login(username, password)
            if success:
                self._on_auth(f"✅ Zalogowano jako {username}", True)
            else:
                self._on_auth("❌ Błędne dane logowania", False)
        except Exception:
            self._on_auth("❌ Brak połączenia z serwerem", False)

    def _push(self) -> None:
        if not self.sync.token:
            self._on_sync_result("⚠️ Najpierw zaloguj się do serwera!", False)
            return
        self._sync_lbl.setStyleSheet("color: #888888; font-size: 11px;")
        self._sync_lbl.setText("⏳ Wysyłanie...")

        def _run():
            import time
            t = time.time()
            try:
                result = self.sync.push(self.db, self.crypto, self.user)
                print(f"Sync Push: {(time.time() - t) * 1000:.1f}ms")
                msg = (f"✅ Wysłano: {result.get('created', 0)} nowych, "
                       f"zaktualizowano: {result.get('updated', 0)}")
                self._sync_sig.emit(msg, True)
            except Exception as e:
                import traceback
                traceback.print_exc()
                self._sync_sig.emit(f"❌ Błąd: {e}", False)

        threading.Thread(target=_run, daemon=True).start()

    def _pull(self) -> None:
        if not self.sync.token:
            self._on_sync_result("⚠️ Najpierw zaloguj się do serwera!", False)
            return
        self._sync_lbl.setStyleSheet("color: #888888; font-size: 11px;")
        self._sync_lbl.setText("⏳ Pobieranie...")

        def _run():
            import time
            t = time.time()
            try:
                result = self.sync.pull(self.db, self.crypto, self.user)
                print(f"Sync Pull: {(time.time() - t) * 1000:.1f}ms")
                msg = (f"✅ Zaimportowano: {result['imported']} nowych, "
                       f"pominięto: {result['skipped']}")
                self._sync_sig.emit(msg, True)
                if self.on_refresh:
                    self.on_refresh()
            except Exception as e:
                self._sync_sig.emit(f"❌ Błąd: {e}", False)

        threading.Thread(target=_run, daemon=True).start()
