"""
logger.py - System logowania aplikacji AegisVault
==================================================
Inicjalizowany AUTOMATYCZNIE przy pierwszym imporcie — nie czeka na setup_logging().
Logi zapisywane w folderze instalacji programu (obok .exe) lub w katalogu projektu:
  {install_dir}/logs/aegisvault_YYYY-MM-DD.log
"""

import logging
import os
import sys
from datetime import datetime, timedelta

# ── Inicjalizacja przy imporcie ────────────────────────────────────────────

_LOG_DIR: str = ""
_log_file: str = ""


def _bootstrap() -> None:
    """Inicjalizuje logger natychmiast przy imporcie modułu."""
    global _LOG_DIR, _log_file

    # Wyznacz katalog logów — folder instalacji (obok .exe) lub katalog projektu
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    _LOG_DIR = os.path.join(base, "logs")

    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
    except Exception:
        pass  # nie mamy gdzie pisać — fallback do stderr poniżej

    _log_file = os.path.join(_LOG_DIR, f"aegisvault_{datetime.now().strftime('%Y-%m-%d')}.log")

    root = logging.getLogger("aegisvault")
    root.setLevel(logging.DEBUG)

    if root.handlers:
        return  # już zainicjalizowany (np. przy reloadzie modułu)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )

    # Handler pliku
    try:
        fh = logging.FileHandler(_log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception as e:
        # Fallback — logi idą na stderr
        sh = logging.StreamHandler()
        sh.setLevel(logging.DEBUG)
        sh.setFormatter(fmt)
        root.addHandler(sh)
        root.warning(f"Nie można otworzyć pliku logu ({_log_file}): {e} — logging do stderr")

    root.info(f"=== AegisVault uruchomiony | log: {_log_file} ===")


_bootstrap()


# ── Publiczne API ──────────────────────────────────────────────────────────

def get_logger(name: str) -> logging.Logger:
    """Zwraca logger dla modułu. Użycie: logger = get_logger(__name__)"""
    return logging.getLogger(f"aegisvault.{name}")


def setup_logging(retention_days: int = 7) -> None:
    """Ustawia retencję i czyści stare logi. Wywołaj po załadowaniu preferencji."""
    logging.getLogger("aegisvault").info(f"Retencja logów: {retention_days} dni")
    cleanup_old_logs(retention_days)


def cleanup_old_logs(retention_days: int) -> int:
    """Usuwa pliki logów starsze niż retention_days dni. Zwraca liczbę usuniętych."""
    if not _LOG_DIR or not os.path.isdir(_LOG_DIR):
        return 0
    cutoff = datetime.now() - timedelta(days=retention_days)
    removed = 0
    for fname in os.listdir(_LOG_DIR):
        if not fname.startswith("aegisvault_") or not fname.endswith(".log"):
            continue
        try:
            date_str = fname[len("aegisvault_"):-len(".log")]
            file_date = datetime.strptime(date_str, "%Y-%m-%d")
            if file_date < cutoff:
                os.remove(os.path.join(_LOG_DIR, fname))
                removed += 1
        except (ValueError, OSError):
            pass
    return removed
