"""Read-side queries used by the API."""
from __future__ import annotations

import re
import sqlite3
from datetime import timedelta

from .dates import from_iso, to_iso, utcnow

_TOKEN = re.compile(r"[\w$&.'-]+", re.UNICODE)


def fts_query(q: str) -> str:
    """User text → safe FTS5 query: every term quoted (AND), last term prefix-matched."""
    terms = [t.strip(".'-") for t in _TOKEN.findall(q or "")]
    terms = [t.replace('"', "") for t in terms if t]
    if not terms:
        return ""
    quoted = [f'"{t}"' for t in terms]
    quoted[-1] += "*"
    return " ".join(quoted)


def _in(values: list[str]) -> str:
    return ",".join("?" * len(values))


def matching_cluster_ids(
    conn: sqlite3.Connection,
    q: str = "",
    sources: list[str] | None = None,
    categories: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[int]:
    """Clusters with at least one item matching the item-level filters (search, source, date)
    and whose category matches. Newest activity first."""
    where, params = ["i.cluster_id IS NOT NULL"], []
    match = fts_query(q)
    if match:
        where.append("i.id IN (SELECT rowid FROM items_fts WHERE items_fts MATCH ?)")
        params.append(match)
    if sources:
        where.append(f"i.source IN ({_in(sources)})")
        params += sources
    if date_from:
        where.append("i.published_at >= ?")
        params.append(date_from)
    if date_to:
        where.append("i.published_at < ?")
        params.append(date_to)
    if categories:
        where.append(f"c.category IN ({_in(categories)})")
        params += categories
    sql = (
        "SELECT c.id FROM items i JOIN clusters c ON c.id = i.cluster_id WHERE "
        + " AND ".join(where)
        + " GROUP BY c.id ORDER BY c.last_published DESC, c.id DESC"
    )
    return [r[0] for r in conn.execute(sql, params)]


def load_clusters(conn: sqlite3.Connection, ids: list[int]) -> list[dict]:
    if not ids:
        return []
    out: dict[int, dict] = {}
    for chunk_start in range(0, len(ids), 500):
        chunk = ids[chunk_start : chunk_start + 500]
        for r in conn.execute(f"SELECT * FROM clusters WHERE id IN ({_in(chunk)})", chunk):
            c = dict(r)
            c.update(items=[], firms=[], sources=[])
            out[c["id"]] = c
        for r in conn.execute(
            f"SELECT id, title, url, source, published_at, published_estimated, description, cluster_id, aum_usd "
            f"FROM items WHERE cluster_id IN ({_in(chunk)}) ORDER BY published_at, id",
            chunk,
        ):
            out[r["cluster_id"]]["items"].append(dict(r))
        for r in conn.execute(
            f"SELECT i.cluster_id, f.firm, MIN(i.published_at) AS first FROM item_firms f JOIN items i ON i.id = f.item_id "
            f"WHERE i.cluster_id IN ({_in(chunk)}) GROUP BY i.cluster_id, f.firm ORDER BY first",
            chunk,
        ):
            out[r["cluster_id"]]["firms"].append(r["firm"])
    result = []
    for cid in ids:
        c = out.get(cid)
        if not c:
            continue
        seen = set()
        for it in c["items"]:
            if it["source"] not in seen:
                seen.add(it["source"])
                c["sources"].append({"name": it["source"], "url": it["url"], "published_at": it["published_at"]})
        c["description"] = next((it["description"] for it in c["items"] if it["description"]), "")
        result.append(c)
    return result


def trending_firms(conn: sqlite3.Connection, days: int = 7, limit: int = 15, now=None) -> list[dict]:
    now = now or utcnow()
    since = to_iso(now - timedelta(days=days))
    rows = conn.execute(
        "SELECT f.firm, COUNT(DISTINCT i.cluster_id) AS stories FROM item_firms f JOIN items i ON i.id = f.item_id "
        "JOIN clusters c ON c.id = i.cluster_id WHERE c.last_published >= ? GROUP BY f.firm "
        "ORDER BY stories DESC, f.firm LIMIT ?",
        (since, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def date_bounds(conn: sqlite3.Connection) -> tuple[str | None, str | None]:
    r = conn.execute("SELECT MIN(published_at), MAX(published_at) FROM items").fetchone()
    return r[0], r[1]


def within_days(iso: str, days: int, now=None) -> bool:
    now = now or utcnow()
    return from_iso(iso) >= now - timedelta(days=days)


def cluster_texts(conn: sqlite3.Connection, ids: list[int]) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {cid: [] for cid in ids}
    for start in range(0, len(ids), 500):
        chunk = ids[start : start + 500]
        for r in conn.execute(f"SELECT cluster_id, title, description FROM items WHERE cluster_id IN ({_in(chunk)})", chunk):
            out[r["cluster_id"]] += [r["title"], r["description"]]
    return out


def watch_hits(conn: sqlite3.Connection, ids: list[int], matcher) -> dict[int, list[str]]:
    return {cid: matcher.hits(*texts) for cid, texts in cluster_texts(conn, ids).items()}
