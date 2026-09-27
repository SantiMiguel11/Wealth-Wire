"""Filesystem locations.

Config (the editable YAML files) lives in the repo root unless FIDUCIARYWIRE_CONFIG points elsewhere
(the pre-rename WEALTHWIRE_* variable names are still read as a fallback).
Runtime data (SQLite DB, SOURCES.md, digests/, weekly/, _work/) lives in the repo root unless
FIDUCIARYWIRE_HOME points elsewhere — used for the offline demo dataset, tests and the refresh workflow.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"      # the only rendering code; copied verbatim into site/
SCHEMAS_DIR = ROOT / "schemas"        # JSON Schemas for site/data/*.json


DB_NAME = "fiduciarywire.db"
LEGACY_DB_NAMES = ("wealthwire.db",)  # the project's earlier name; moved to DB_NAME on first use


def env(name: str) -> str | None:
    """FIDUCIARYWIRE_<name>, falling back to the pre-rename WEALTHWIRE_<name> so old shells and scheduled tasks
    keep working."""
    return os.environ.get("FIDUCIARYWIRE_" + name) or os.environ.get("WEALTHWIRE_" + name)


def config_dir() -> Path:
    return Path(env("CONFIG") or ROOT)


def data_home() -> Path:
    return Path(env("HOME") or ROOT)


def db_path() -> Path:
    return data_home() / "data" / DB_NAME


def sources_md_path() -> Path:
    return data_home() / "SOURCES.md"


def digests_dir() -> Path:
    return data_home() / "digests"


def weekly_dir() -> Path:
    return data_home() / "weekly"


def work_dir() -> Path:
    """Scratch files for one refresh (AI inputs/outputs). Never published."""
    return data_home() / "_work"


def firm_eval_path() -> Path:
    return data_home() / "firm_eval.json"


def wire_stats_path() -> Path:
    """Per-run, per-feed counts for the press-release wires (kept in private state on `live`)."""
    return data_home() / "wire_stats.csv"
