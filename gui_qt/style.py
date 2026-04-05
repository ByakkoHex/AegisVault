"""
style.py — Globalny QSS dla AegisVault (PyQt6)
==============================================
Jeden plik zamiast rozsianych kolorów po każdym widgecie.
Zmiana motywu = app.setStyleSheet(build_qss(accent, dark=True/False)).

Kolory bazowe zgodne ze starym CTk UI:
  Dark BG:  #1a1a1a   Card: #1e1e1e   Row: #2a2a2a
  Accent:   #4F8EF7   Hover: #3a7ae0
  Red:      #e05252   Green: #4caf50  Orange: #f0a500
"""

from utils.prefs_manager import PrefsManager


def build_qss(accent: str = "#4F8EF7", dark: bool = True) -> str:
    """Buduje kompletny QSS string dla wybranego motywu i koloru akcentu."""

    if dark:
        bg          = "#1a1a1a"
        bg_card     = "#1e1e1e"
        bg_row      = "#2a2a2a"
        bg_input    = "#252525"
        bg_hover    = "#2f2f2f"
        bg_sidebar  = "#161616"
        border      = "#333333"
        border_focus= accent
        text        = "#f0f0f0"
        text_muted  = "#888888"
        scrollbar   = "#2e2e2e"
        scrollhandle= "#4a4a4a"
        tab_active  = "#252525"
        tab_inactive= "#1a1a1a"
        sep_color   = "#2a2a2a"
    else:
        bg          = "#f5f5f5"
        bg_card     = "#ffffff"
        bg_row      = "#eeeeee"
        bg_input    = "#ffffff"
        bg_hover    = "#e8e8e8"
        bg_sidebar  = "#ebebeb"
        border      = "#d0d0d0"
        border_focus= accent
        text        = "#1a1a1a"
        text_muted  = "#666666"
        scrollbar   = "#e0e0e0"
        scrollhandle= "#b0b0b0"
        tab_active  = "#ffffff"
        tab_inactive= "#f0f0f0"
        sep_color   = "#d8d8d8"

    # Kolor hover akcentu — rozjaśniony lub przyciemniony
    accent_hover = _darken(accent, 0.15) if not dark else _lighten(accent, 0.10)
    accent_dim   = _alpha_blend(accent, bg, 0.15)  # bardzo subtelny bg dla zaznaczonych wierszy

    return f"""
/* ── Globalne ─────────────────────────────────────────────────────── */
QWidget {{
    background-color: {bg};
    color: {text};
    font-family: "Segoe UI", "SF Pro Text", "Ubuntu", "Helvetica Neue", sans-serif;
    font-size: 13px;
    outline: none;
}}

QMainWindow {{
    background-color: {bg};
}}

/* ── Przyciski ────────────────────────────────────────────────────── */
QPushButton {{
    background-color: {accent};
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 8px 18px;
    font-size: 13px;
    font-weight: 500;
    min-height: 32px;
}}
QPushButton:hover  {{ background-color: {accent_hover}; }}
QPushButton:pressed {{ background-color: {_darken(accent, 0.25)}; }}
QPushButton:disabled {{ background-color: {border}; color: {text_muted}; }}

QPushButton[flat="true"] {{
    background-color: transparent;
    color: {accent};
    padding: 6px 12px;
}}
QPushButton[flat="true"]:hover {{
    background-color: {bg_hover};
}}

QPushButton[danger="true"] {{
    background-color: #e05252;
}}
QPushButton[danger="true"]:hover {{
    background-color: #c43e3e;
}}

QPushButton[secondary="true"] {{
    background-color: {bg_row};
    color: {text};
    border: 1px solid {border};
}}
QPushButton[secondary="true"]:hover {{
    background-color: {bg_hover};
}}

/* ── Inputy ───────────────────────────────────────────────────────── */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {bg_input};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 8px 12px;
    color: {text};
    font-size: 13px;
    selection-background-color: {accent};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {border_focus};
}}
QLineEdit:disabled {{
    background-color: {bg};
    color: {text_muted};
}}

/* ── Etykiety ─────────────────────────────────────────────────────── */
QLabel {{
    background-color: transparent;
    color: {text};
}}
QLabel[muted="true"]   {{ color: {text_muted}; font-size: 12px; }}
QLabel[heading="true"] {{ font-size: 16px; font-weight: 600; }}
QLabel[accent="true"]  {{ color: {accent}; }}

/* ── ComboBox ─────────────────────────────────────────────────────── */
QComboBox {{
    background-color: {bg_input};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 6px 12px;
    color: {text};
    min-height: 32px;
}}
QComboBox:focus {{ border-color: {border_focus}; }}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background-color: {bg_card};
    border: 1px solid {border};
    border-radius: 8px;
    color: {text};
    selection-background-color: {accent};
}}

/* ── CheckBox / RadioButton ───────────────────────────────────────── */
QCheckBox, QRadioButton {{
    background-color: transparent;
    color: {text};
    spacing: 8px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {border};
    border-radius: 4px;
    background-color: {bg_input};
}}
QCheckBox::indicator:checked {{
    background-color: {accent};
    border-color: {accent};
}}

/* ── Slider ───────────────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    height: 4px;
    background: {border};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {accent};
    border: none;
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}}
QSlider::sub-page:horizontal {{
    background: {accent};
    border-radius: 2px;
}}

/* ── Scrollbar ────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {scrollhandle};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {accent}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
}}
QScrollBar::handle:horizontal {{
    background: {scrollhandle};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── TabWidget ────────────────────────────────────────────────────── */
QTabWidget::pane {{
    background-color: {bg_card};
    border: 1px solid {border};
    border-radius: 8px;
    border-top-left-radius: 0;
}}
QTabBar::tab {{
    background-color: {tab_inactive};
    color: {text_muted};
    padding: 8px 20px;
    border: 1px solid {border};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-size: 12px;
}}
QTabBar::tab:selected {{
    background-color: {tab_active};
    color: {text};
    border-bottom-color: {tab_active};
    font-weight: 500;
}}
QTabBar::tab:hover:!selected {{ background-color: {bg_hover}; }}

/* ── ProgressBar ──────────────────────────────────────────────────── */
QProgressBar {{
    background-color: {bg_row};
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {accent};
    border-radius: 4px;
}}

/* ── Menu / ContextMenu ───────────────────────────────────────────── */
QMenu {{
    background-color: {bg_card};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 4px;
    color: {text};
}}
QMenu::item {{
    padding: 8px 24px 8px 12px;
    border-radius: 6px;
}}
QMenu::item:selected {{ background-color: {bg_hover}; }}
QMenu::separator {{
    height: 1px;
    background: {border};
    margin: 4px 8px;
}}

/* ── ToolTip ──────────────────────────────────────────────────────── */
QToolTip {{
    background-color: {bg_card};
    color: {text};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}

/* ── Dialogs ──────────────────────────────────────────────────────── */
QDialog {{
    background-color: {bg};
}}

/* ── Separator ────────────────────────────────────────────────────── */
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {sep_color};
}}
"""


def _darken(hex_color: str, amount: float) -> str:
    r, g, b = _parse(hex_color)
    r = max(0, int(r * (1 - amount)))
    g = max(0, int(g * (1 - amount)))
    b = max(0, int(b * (1 - amount)))
    return f"#{r:02x}{g:02x}{b:02x}"


def _lighten(hex_color: str, amount: float) -> str:
    r, g, b = _parse(hex_color)
    r = min(255, int(r + (255 - r) * amount))
    g = min(255, int(g + (255 - g) * amount))
    b = min(255, int(b + (255 - b) * amount))
    return f"#{r:02x}{g:02x}{b:02x}"


def _alpha_blend(fg: str, bg: str, alpha: float) -> str:
    fr, fg_, fb = _parse(fg)
    br, bg_c, bb = _parse(bg)
    r = int(br + (fr - br) * alpha)
    g = int(bg_c + (fg_ - bg_c) * alpha)
    b = int(bb + (fb - bb) * alpha)
    return f"#{r:02x}{g:02x}{b:02x}"


def _parse(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def current_dark() -> bool:
    """Zwraca True jeśli aktualny motyw jest ciemny."""
    prefs = PrefsManager()
    mode = prefs.get("appearance_mode") or "dark"
    return mode.lower() != "light"


def current_qss() -> str:
    """Buduje QSS z aktualnych ustawień użytkownika (PrefsManager)."""
    prefs = PrefsManager()
    accent = prefs.get_accent()
    dark   = current_dark()
    return build_qss(accent=accent, dark=dark)
