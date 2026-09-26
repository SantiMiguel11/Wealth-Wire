"""Recompute all derived data from stored items."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import load_config
from .dates import utcnow


def recompute(conn: sqlite3.Connection, now: datetime | None = None) -> dict:
    cfg = load_config()
    now = now or utcnow()
    n_items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    return {"items": n_items, "clusters": 0, "new_stories": 0,
            "local_date": now.astimezone(ZoneInfo(cfg["timezone"])).date().isoformat()}
