"""
security_analysis_window.py — Dashboard analizy bezpieczeństwa haseł (PyQt6)
=============================================================================
Pokazuje:
- Ogólny wynik bezpieczeństwa
- Słabe hasła
- Zduplikowane hasła
- Stare hasła (>90 dni)
"""

from datetime import datetime, timezone

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QProgressBar,
)
from PyQt6.QtCore import Qt

from utils.password_strength import check_strength
from utils.prefs_manager import PrefsManager


def _accent() -> str:
    return PrefsManager().get_accent()


def _is_dark() -> bool:
    from gui_qt.style import current_dark
    try:
        return current_dark()
    except Exception:
        return True


def _blend(accent: str, base: str, alpha: float) -> str:
    def _p(c):
        c = c.lstrip("#")
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    ar, ag, ab = _p(accent)
    br, bg_, bb = _p(base)
    return (f"#{int(br + (ar - br) * alpha):02x}"
            f"{int(bg_ + (ag - bg_) * alpha):02x}"
            f"{int(bb + (ab - bb) * alpha):02x}")


class SecurityAnalysisWindow(QDialog):
    def __init__(self, parent: QWidget, db, crypto, user):
        super().__init__(parent)
        self.db     = db
        self.crypto = crypto
        self.user   = user
        self._accent = _accent()

        self.setWindowTitle("Analiza bezpieczeństwa")
        self.setFixedSize(560, 680)
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)

        self._analyse()
        self._build_ui()

        from PyQt6.QtCore import QPropertyAnimation, QEasingCurve
        self.setWindowOpacity(0.0)
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(150)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._fade_anim.start()

    # ──────────────────────────────────────────────────────────────────
    # ANALIZA
    # ──────────────────────────────────────────────────────────────────

    def _analyse(self):
        entries = self.db.get_all_passwords(self.user)
        self.total      = len(entries)
        self.weak       = []
        self.duplicates = []
        self.old        = []

        password_map: dict = {}

        for entry in entries:
            try:
                plaintext = self.db.decrypt_password(entry, self.crypto)
            except Exception:
                continue

            strength = check_strength(plaintext)
            if strength["score"] <= 1:
                self.weak.append((entry, strength))

            if plaintext not in password_map:
                password_map[plaintext] = []
            password_map[plaintext].append(entry)

            if entry.updated_at:
                now     = datetime.now()
                updated = entry.updated_at
                if hasattr(updated, "tzinfo") and updated.tzinfo:
                    now = datetime.now(timezone.utc)
                days_old = (now - updated).days
                if days_old > 90:
                    self.old.append((entry, days_old))

        for pwd, ents in password_map.items():
            if len(ents) > 1:
                self.duplicates.append(ents)

        issues = len(self.weak) + len(self.duplicates) + len(self.old)
        if self.total == 0:
            self.security_score = 100
        else:
            penalty = min(100, issues * 15)
            self.security_score = max(0, 100 - penalty)

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
        acc   = self._accent

        self.setStyleSheet(f"""
            QDialog {{
                background: {bg};
                border: 1px solid {brd};
                border-radius: 12px;
            }}
            QLabel {{ color: {fg}; background: transparent; }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 16)
        root.setSpacing(0)

        # ── Nagłówek ────────────────────────────────────────────
        hdr_tint = _blend(acc, card, 0.18)
        hdr = QFrame()
        hdr.setFixedHeight(70)
        hdr.setStyleSheet(f"""
            QFrame {{
                background: {hdr_tint};
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }}
        """)
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(20, 0, 20, 0)

        title_lbl = QLabel("🛡️  Analiza bezpieczeństwa")
        title_lbl.setStyleSheet(f"color: {fg}; font-size: 19px; font-weight: bold;")
        hdr_lay.addWidget(title_lbl, 1)

        count_lbl = QLabel(f"Przeanalizowano {self.total} haseł")
        count_lbl.setStyleSheet(f"color: {acc}; font-size: 12px;")
        hdr_lay.addWidget(count_lbl)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {sub};
                border: none;
                font-size: 13px;
                border-radius: 14px;
                margin-left: 12px;
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

        # ── Score card ──────────────────────────────────────────
        root.addLayout(self._padded(self._build_score_card(dark, fg, sub, brd, acc)))
        root.addSpacing(4)

        # ── Scrollable sections ─────────────────────────────────
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: {bg};
                width: 6px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {"#3a3a3a" if dark else "#cccccc"};
                border-radius: 3px;
                min-height: 20px;
            }}
        """)

        scroll_inner = QWidget()
        scroll_inner.setStyleSheet("background: transparent;")
        scroll_lay = QVBoxLayout(scroll_inner)
        scroll_lay.setContentsMargins(16, 8, 16, 8)
        scroll_lay.setSpacing(4)

        if self.total == 0:
            empty = QLabel("Nie masz jeszcze żadnych haseł do analizy.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(f"color: {sub}; font-size: 13px; margin: 30px 0;")
            scroll_lay.addWidget(empty)
        else:
            self._build_section(scroll_lay,
                f"⚠️  Słabe hasła ({len(self.weak)})",
                self.weak, self._render_weak, "#dd6b20", dark, fg)
            self._build_section(scroll_lay,
                f"🔄  Zduplikowane hasła ({len(self.duplicates)})",
                self.duplicates, self._render_duplicate, "#805ad5", dark, fg)
            self._build_section(scroll_lay,
                f"🕐  Stare hasła >90 dni ({len(self.old)})",
                self.old, self._render_old, "#2b6cb0", dark, fg)

            if not self.weak and not self.duplicates and not self.old:
                ok_lbl = QLabel(
                    "✅  Wszystkie hasła wyglądają dobrze!\nNie wykryto żadnych problemów."
                )
                ok_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                ok_lbl.setStyleSheet("color: #38a169; font-size: 14px; margin: 30px 0;")
                scroll_lay.addWidget(ok_lbl)

        scroll_lay.addStretch()
        scroll_area.setWidget(scroll_inner)
        root.addWidget(scroll_area, 1)

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

    def _padded(self, widget: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(16, 0, 16, 0)
        row.addWidget(widget)
        return row

    def _build_score_card(self, dark, fg, sub, brd, acc) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {"#1e1e1e" if dark else "#ffffff"};
                border: 1px solid {brd};
                border-radius: 16px;
            }}
        """)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)

        if self.security_score >= 80:
            score_color = "#38a169"
            score_icon  = "🟢"
        elif self.security_score >= 50:
            score_color = "#d69e2e"
            score_icon  = "🟡"
        else:
            score_color = "#e53e3e"
            score_icon  = "🔴"

        # Tytuł + wynik
        top = QHBoxLayout()
        score_title = QLabel(f"{score_icon}  Wynik bezpieczeństwa")
        score_title.setStyleSheet(f"color: {fg}; font-size: 14px; font-weight: bold; background: transparent;")
        top.addWidget(score_title, 1)
        score_val = QLabel(f"{self.security_score}/100")
        score_val.setStyleSheet(f"color: {score_color}; font-size: 22px; font-weight: bold; background: transparent;")
        top.addWidget(score_val)
        lay.addLayout(top)

        # Pasek postępu
        bar = QProgressBar()
        bar.setFixedHeight(10)
        bar.setRange(0, 100)
        bar.setValue(self.security_score)
        bar.setTextVisible(False)
        bar_bg = "#2e2e2e" if dark else "#e0e0e0"
        bar.setStyleSheet(f"""
            QProgressBar {{
                background: {bar_bg};
                border: none;
                border-radius: 5px;
            }}
            QProgressBar::chunk {{
                background: {score_color};
                border-radius: 5px;
            }}
        """)
        lay.addWidget(bar)

        # Statystyki
        stats_frame = QFrame()
        stats_bg = "#161616" if dark else "#f5f5f5"
        stats_frame.setStyleSheet(f"""
            QFrame {{
                background: {stats_bg};
                border-radius: 10px;
                border: none;
            }}
        """)
        stats_lay = QHBoxLayout(stats_frame)
        stats_lay.setContentsMargins(0, 10, 0, 10)
        stats_lay.setSpacing(0)

        safe_count = max(0, self.total - len(self.weak) - len(self.duplicates))
        for count, lbl_text, color in [
            (len(self.weak),       "⚠️ Słabe",     "#dd6b20"),
            (len(self.duplicates), "🔄 Duplikaty",  "#805ad5"),
            (len(self.old),        "🕐 Stare",      "#2b6cb0"),
            (safe_count,           "✅ Bezpieczne", "#38a169"),
        ]:
            col_w = QWidget()
            col_w.setStyleSheet("background: transparent;")
            col_lay = QVBoxLayout(col_w)
            col_lay.setContentsMargins(0, 0, 0, 0)
            col_lay.setSpacing(2)
            col_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

            num_lbl = QLabel(str(count))
            num_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            num_lbl.setStyleSheet(f"color: {color}; font-size: 20px; font-weight: bold; background: transparent;")
            col_lay.addWidget(num_lbl)

            tag_lbl = QLabel(lbl_text)
            tag_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tag_lbl.setStyleSheet(f"color: {sub}; font-size: 11px; background: transparent;")
            col_lay.addWidget(tag_lbl)

            stats_lay.addWidget(col_w, 1)

        lay.addWidget(stats_frame)
        return card

    def _build_section(self, parent_lay: QVBoxLayout, title: str, items, render_fn,
                       color: str, dark: bool, fg: str):
        if not items:
            return

        hdr_lbl = QLabel(title)
        hdr_lbl.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: bold; margin-top: 12px;")
        parent_lay.addWidget(hdr_lbl)

        for item in items:
            parent_lay.addWidget(render_fn(item, dark, fg))

    def _render_weak(self, item: tuple, dark: bool, fg: str) -> QFrame:
        entry, strength = item
        row_bg  = "#2a1f10" if dark else "#fff8f0"
        row_brd = "#7a4a10" if dark else "#f6ad55"

        row = QFrame()
        row.setStyleSheet(f"""
            QFrame {{
                background: {row_bg};
                border: 1px solid {row_brd};
                border-radius: 10px;
            }}
        """)
        lay = QVBoxLayout(row)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)

        title_lbl = QLabel(entry.title)
        title_lbl.setStyleSheet(f"color: {fg}; font-size: 13px; font-weight: bold; background: transparent;")
        lay.addWidget(title_lbl)

        info_lbl = QLabel(
            f"Siła: {strength['label']}  •  Entropia: {strength['entropy']} bit"
        )
        info_lbl.setStyleSheet("color: #888888; font-size: 11px; background: transparent;")
        lay.addWidget(info_lbl)

        if strength.get("suggestions"):
            tip_lbl = QLabel(f"💡 {strength['suggestions'][0]}")
            tip_lbl.setStyleSheet("color: #dd6b20; font-size: 11px; background: transparent;")
            lay.addWidget(tip_lbl)

        return row

    def _render_duplicate(self, group: list, dark: bool, fg: str) -> QFrame:
        names   = ", ".join(e.title for e in group)
        row_bg  = "#1f1030" if dark else "#f8f0ff"
        row_brd = "#5a3090" if dark else "#b794f4"

        row = QFrame()
        row.setStyleSheet(f"""
            QFrame {{
                background: {row_bg};
                border: 1px solid {row_brd};
                border-radius: 10px;
            }}
        """)
        lay = QVBoxLayout(row)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(2)

        title_lbl = QLabel(f"Takie samo hasło w: {names}")
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet("color: #805ad5; font-size: 13px; font-weight: bold; background: transparent;")
        lay.addWidget(title_lbl)

        tip_lbl = QLabel("💡 Użyj unikalnego hasła dla każdego serwisu")
        tip_lbl.setStyleSheet("color: #888888; font-size: 11px; background: transparent;")
        lay.addWidget(tip_lbl)

        return row

    def _render_old(self, item: tuple, dark: bool, fg: str) -> QFrame:
        entry, days = item
        row_bg  = "#101830" if dark else "#f0f4ff"
        row_brd = "#1a3a70" if dark else "#76b0f5"

        row = QFrame()
        row.setStyleSheet(f"""
            QFrame {{
                background: {row_bg};
                border: 1px solid {row_brd};
                border-radius: 10px;
            }}
        """)
        lay = QVBoxLayout(row)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)

        title_lbl = QLabel(entry.title)
        title_lbl.setStyleSheet(f"color: {fg}; font-size: 13px; font-weight: bold; background: transparent;")
        lay.addWidget(title_lbl)

        age_lbl = QLabel(f"Ostatnia zmiana: {days} dni temu")
        age_lbl.setStyleSheet("color: #888888; font-size: 11px; background: transparent;")
        lay.addWidget(age_lbl)

        tip_lbl = QLabel("💡 Rozważ zmianę tego hasła")
        tip_lbl.setStyleSheet("color: #2b6cb0; font-size: 11px; background: transparent;")
        lay.addWidget(tip_lbl)

        return row
