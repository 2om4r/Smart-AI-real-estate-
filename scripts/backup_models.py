"""
scripts/backup_models.py — Daily Model Registry Backup
=======================================================
يَنسخ النموذج النشط إلى مجلد backups/ يومياً مع retention 30 يوماً.

Usage:
    # Manual run
    python scripts/backup_models.py

    # Auto via scheduler (added to extensions.py)
    Scheduled daily at 3 AM
"""
from __future__ import annotations

import os
import sys
import shutil
import logging
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).parent.parent
REGISTRY_DIR = PROJECT_ROOT / "models" / "registry"
BACKUP_DIR   = PROJECT_ROOT / "models" / "backups"

RETENTION_DAYS = 30   # delete backups older than this


def run() -> dict:
    """Copy current active model to backups/ + prune old backups."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. Find the active model ─────────────────────────────────
    latest = REGISTRY_DIR / "latest.pkl"
    if not latest.exists() or not latest.is_symlink():
        logger.warning(f"No active model at {latest}")
        return {'status': 'no_model'}

    src = latest.resolve()
    if not src.exists():
        logger.warning(f"Symlink target missing: {src}")
        return {'status': 'no_target'}

    # ── 2. Copy with date-stamped name ──────────────────────────
    today    = datetime.utcnow().strftime('%Y%m%d')
    dest     = BACKUP_DIR / f"backup_{today}_{src.name}"

    if dest.exists():
        logger.info(f"Backup already exists for today: {dest.name}")
        backed_up = False
    else:
        shutil.copy2(src, dest)
        logger.info(f"✅ Backed up: {dest.name} ({dest.stat().st_size / 1024 / 1024:.1f} MB)")
        backed_up = True

    # ── 3. Prune old backups ─────────────────────────────────────
    cutoff = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
    pruned = 0
    for f in BACKUP_DIR.glob("backup_*.pkl"):
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if mtime < cutoff:
            try:
                f.unlink()
                pruned += 1
                logger.info(f"Pruned old backup: {f.name}")
            except Exception as e:
                logger.warning(f"Could not prune {f}: {e}")

    # ── 4. Summary ───────────────────────────────────────────────
    remaining = list(BACKUP_DIR.glob("backup_*.pkl"))
    return {
        'status':      'success',
        'backed_up':   backed_up,
        'destination': str(dest) if backed_up else None,
        'pruned':      pruned,
        'total_backups': len(remaining),
        'retention_days': RETENTION_DAYS,
    }


if __name__ == "__main__":
    result = run()
    print(result)
    sys.exit(0 if result['status'] == 'success' else 1)
