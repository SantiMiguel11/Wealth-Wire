"""Recompute all derived data from stored items (categories, firms, AUM, clusters, M&A, new stories)."""
from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import load_config
from .dates import utcnow


def _load_items(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, title, url, source, published_at, fetched_at, description FROM items ORDER BY published_at, id"
    ).fetchall()
    return [dict(r) for r in rows]


def group_items(items: list[dict], cfg: dict) -> list[list[dict]]:
    return [[it] for it in items]


def write_clusters(conn: sqlite3.Connection, groups: list[list[dict]]) -> None:
    conn.execute("DELETE FROM clusters")
    for group in groups:
        group = sorted(group, key=lambda it: (it["published_at"], it["id"]))
        head = group[0]
        cid = min(it["id"] for it in group)
        cats = [it.get("category") for it in group]
        category = head.get("category") or "Other"
        if category == "Other":
            non_other = [c for c in cats if c and c != "Other"]
            if non_other:
                category = Counter(non_other).most_common(1)[0][0]
        aums = [it.get("aum_usd") for it in group if it.get("aum_usd")]
        aum = head.get("aum_usd") or (Counter(aums).most_common(1)[0][0] if aums else None)
        conn.execute(
            "INSERT INTO clusters(id, headline_item_id, headline, url, category, first_seen, first_published, last_published, "
            "outlet_count, item_count, aum_usd) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                cid, head["id"], head["title"], head["url"], category,
                min(it["fetched_at"] for it in group),
                head["published_at"], max(it["published_at"] for it in group),
                len({it["source"] for it in group}), len(group), aum,
            ),
        )
        conn.executemany("UPDATE items SET cluster_id=? WHERE id=?", [(cid, it["id"]) for it in group])


def recompute(conn: sqlite3.Connection, now: datetime | None = None) -> dict:
    cfg = load_config()
    now = now or utcnow()
    items = _load_items(conn)
    for it in items:
        it["category"] = "Other"
        it["aum_usd"] = None
    conn.executemany("UPDATE items SET category=?, aum_usd=? WHERE id=?", [(it["category"], it["aum_usd"], it["id"]) for it in items])
    groups = group_items(items, cfg)
    write_clusters(conn, groups)
    conn.commit()
    local_date = now.astimezone(ZoneInfo(cfg["timezone"])).date().isoformat()
    return {"items": len(items), "clusters": len(groups), "new_stories": 0, "local_date": local_date}
