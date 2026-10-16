"""Paths, settings defaults and logging for FinPilot."""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

from . import __app_name__

_PKG_DIR = Path(__file__).resolve().parent


def resource_path(*parts: str) -> Path:
    """Locate a bundled resource both from source and inside a PyInstaller build."""
    base = Path(getattr(sys, "_MEIPASS", "")) / "finpilot" if hasattr(sys, "_MEIPASS") else _PKG_DIR
    return base.joinpath(*parts)


def data_dir() -> Path:
    """Per-user writable data folder (database, autosaves, logs, backups).

    Windows: %APPDATA%\\FinPilot. Elsewhere: ~/.local/share/FinPilot.
    Override with the FINPILOT_HOME environment variable (used by tests).
    """
    override = os.environ.get("FINPILOT_HOME")
    if override:
        p = Path(override)
    elif sys.platform == "win32":
        p = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / __app_name__
    else:
        p = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / __app_name__
    p.mkdir(parents=True, exist_ok=True)
    return p


def _documents_dir() -> Path:
    """The user's real Documents folder (follows OneDrive/known-folder redirection on Windows)."""
    try:
        from PySide6.QtCore import QStandardPaths
        loc = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        if loc:
            return Path(loc)
    except Exception:
        pass
    return Path.home() / "Documents"


def projects_dir() -> Path:
    override = os.environ.get("FINPILOT_HOME")
    p = (Path(override) / "Projects") if override else (_documents_dir() / f"{__app_name__} Projects")
    p.mkdir(parents=True, exist_ok=True)
    return p


def autosave_dir() -> Path:
    p = data_dir() / "autosave"
    p.mkdir(exist_ok=True)
    return p


def backups_dir() -> Path:
    p = data_dir() / "backups"
    p.mkdir(exist_ok=True)
    return p


def setup_logging(level: int = logging.INFO) -> Path:
    log_dir = data_dir() / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "finpilot.log"
    root = logging.getLogger()
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        h = logging.handlers.RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(h)
    root.setLevel(level)
    return log_file
