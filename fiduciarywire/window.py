"""Top Stories window and ranking (§1, §2).

Window: clusters first seen since the previous successful refresh, but never less than 24 hours —
so the first refresh of a day (or after a gap) still covers a full day of news.
Ranking: outlet count, then recency. Watchlist ranking happens in the browser.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from . import db
from .dates import from_iso

MIN_WINDOW = timedelta(hours=24)


def top_window(conn: sqlite3.Connection, now: datetime) -> datetime:
    floor = now - MIN_WINDOW
    prev = db.get_meta(conn, "previous_success")
    if not prev:
        return floor
    try:
        return min(from_iso(prev), floor)
    except ValueError:
        return floor


def rank_clusters(clusters: list[dict]) -> list[dict]:
    """Outlet count (desc), then most recent activity (desc), then id for stability."""
    return sorted(clusters, key=lambda c: (-c["outlet_count"], _neg(c["last_published"]), -c["id"]))


def _neg(iso: str) -> float:
    return -from_iso(iso).timestamp()
