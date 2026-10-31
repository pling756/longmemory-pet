"""Portable path helpers for the pet."""
from __future__ import annotations

import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent


def data_dir() -> Path:
    """Return the writable data directory (portable by default)."""
    override = os.environ.get("LONGMEM_PET_HOME")
    path = Path(override).expanduser() if override else PROJECT_ROOT / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "memory.sqlite3"


def config_path() -> Path:
    return data_dir() / "config.json"
