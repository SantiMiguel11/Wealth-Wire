"""Recompute all derived data from stored items (categories, firms, AUM, clusters, M&A, new stories)."""
from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from .categorize import Categorizer
from .cluster import ClusterItem, cluster
from .config import load_config, load_stoplist
from .dates import utcnow
from .extract import extract_aum, extract_firms
from .mna import deal_for_cluster
from .watchlist import Matcher, load_watchlist


def _load_items(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, title, url, source, published_at, fetched_at, description FROM items ORDER BY published_at, id"
    ).fetchall()
    return [dict(r) for r in rows]


def group_items(items: list[dict], cfg: dict) -> list[list[dict]]:
    by_id = {it["id"]: it for it in items}
    citems = [
        ClusterItem(it["id"], it["source"], it["published_at"], it["title"], firms=set(it["title_firms"]), category=it["category"])
        for it in items
    ]
    groups = cluster(citems, threshold=float(cfg["cluster"]["threshold"]), window_hours=float(cfg["cluster"]["window_hours"]))
    return [[by_id[c.id] for c in g] for g in groups]


def extract_item(it: dict, stoplist: set[str], matcher: Matcher) -> None:
    """Firms from title and description (separately, so spans never cross fields) + watchlist names."""
    alias_map = matcher.alias_map()
    title_firms = extract_firms(it["title"], stoplist, alias_map)
    firms = list(title_firms)
    for f in extract_firms(it["description"], stoplist, alias_map) + matcher.hits(it["title"], it["description"]):
        if f not in firms:
            firms.append(f)
    for f in matcher.hits(it["title"]):
        if f not in title_firms:
            title_firms.append(f)
    it["title_firms"] = title_firms
    it["firms"] = firms
    it["aum_usd"] = extract_aum(it["title"]) or extract_aum(it["description"])


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


def write_deals(conn: sqlite3.Connection) -> int:
    """One M&A row per M&A-category cluster."""
    conn.execute("DELETE FROM mna_deals")
    rows = conn.execute("SELECT id, first_published FROM clusters WHERE category = 'M&A'").fetchall()
    for r in rows:
        titles = [t[0] for t in conn.execute("SELECT title FROM items WHERE cluster_id=? ORDER BY published_at, id", (r["id"],))]
        d = deal_for_cluster(titles)
        conn.execute(
            "INSERT INTO mna_deals(cluster_id, acquirer, target, target_aum_usd, deal_type, deal_date, confidence, note) VALUES (?,?,?,?,?,?,?,?)",
            (r["id"], d.acquirer, d.target, d.target_aum_usd, d.deal_type, r["first_published"], d.confidence, d.note),
        )
    return len(rows)


def recompute(conn: sqlite3.Connection, now: datetime | None = None) -> dict:
    """Recompute all derived data from the stored items."""
    cfg = load_config()
    now = now or utcnow()
    items = _load_items(conn)
    categorizer = Categorizer()
    stoplist = load_stoplist()
    matcher = Matcher(load_watchlist())
    for it in items:
        it["category"] = categorizer.categorize(it["title"], it["description"])
        extract_item(it, stoplist, matcher)
    conn.executemany("UPDATE items SET category=?, aum_usd=? WHERE id=?", [(it["category"], it["aum_usd"], it["id"]) for it in items])
    conn.execute("DELETE FROM item_firms")
    conn.executemany("INSERT OR IGNORE INTO item_firms(item_id, firm) VALUES (?, ?)", [(it["id"], f) for it in items for f in it["firms"]])
    groups = group_items(items, cfg)
    write_clusters(conn, groups)
    deals = write_deals(conn)
    conn.commit()
    local_date = now.astimezone(ZoneInfo(cfg["timezone"])).date().isoformat()
    return {"items": len(items), "clusters": len(groups), "deals": deals, "local_date": local_date}
