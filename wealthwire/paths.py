"""Filesystem locations.

Config (the editable YAML files) lives in the repo root unless WEALTHWIRE_CONFIG points elsewhere.
Runtime data (SQLite DB, SOURCES.md, new_stories.json, digests/) lives in the repo root unless
WEALTHWIRE_HOME points elsewhere — used for the offline demo dataset and tests.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"


def config_dir() -> Path:
    return Path(os.environ.get("WEALTHWIRE_CONFIG") or ROOT)


def data_home() -> Path:
    return Path(os.environ.get("WEALTHWIRE_HOME") or ROOT)


def db_path() -> Path:
    return data_home() / "data" / "wealthwire.db"


def sources_md_path() -> Path:
    return data_home() / "SOURCES.md"


def new_stories_path() -> Path:
    return data_home() / "new_stories.json"


def digests_dir() -> Path:
    return data_home() / "digests"
