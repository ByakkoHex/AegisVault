"""
auto_backup.py - Automatyczny backup haseł AegisVault
"""
import os
from datetime import datetime, timedelta, timezone
from utils.paths import get_app_data_dir
from utils.logger import get_logger

logger = get_logger(__name__)

BACKUP_INTERVALS = {
    "wyłączony": None,
    "codziennie": timedelta(days=1),
    "co 3 dni": timedelta(days=3),
    "tygodniowo": timedelta(weeks=1),
    "miesięcznie": timedelta(days=30),
}


def get_backup_dir() -> str:
    path = os.path.join(get_app_data_dir(), "backups")
    os.makedirs(path, exist_ok=True)
    return path


def should_backup(prefs) -> bool:
    interval_key = prefs.get("backup_interval") or "wyłączony"
    if interval_key == "wyłączony" or interval_key not in BACKUP_INTERVALS:
        return False
    interval = BACKUP_INTERVALS[interval_key]
    if not interval:
        return False
    last_str = prefs.get("last_backup_at") or ""
    if not last_str:
        return True
    try:
        last = datetime.fromisoformat(last_str)
        return datetime.now(timezone.utc) - last >= interval
    except ValueError:
        return True


def do_backup(db, crypto, user, prefs) -> str | None:
    """Creates backup, returns filepath or None on error."""
    backup_dir = get_backup_dir()
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    filepath = os.path.join(backup_dir, f"backup_{user.username}_{ts}.aegis")
    try:
        count = db.export_passwords(user, crypto, filepath)
        prefs.set("last_backup_at", datetime.now(timezone.utc).isoformat())
        logger.info(f"Auto-backup: {count} haseł → {filepath}")
        _cleanup_old_backups(backup_dir, keep=30)
        return filepath
    except Exception as e:
        logger.error(f"Auto-backup failed: {e}")
        return None


def _cleanup_old_backups(backup_dir: str, keep: int = 30) -> None:
    try:
        files = sorted([
            f for f in os.listdir(backup_dir)
            if f.startswith("backup_") and f.endswith(".aegis")
        ])
        for fname in files[:-keep]:
            try:
                os.remove(os.path.join(backup_dir, fname))
            except OSError:
                pass
    except Exception:
        pass
