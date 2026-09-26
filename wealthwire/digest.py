"""new_stories.json (input for the /digest command) and rendering of digests/YYYY-MM-DD.md."""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import bleach
import markdown

from . import paths, queries
from .dates import from_iso, to_iso
from .watchlist import Matcher, load_watchlist

LAST_DIGEST = ".last_digest"
BACKFILL_GUARD_HOURS = 72
_DIGEST_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")


def read_last_digest(digests: Path) -> datetime | None:
    p = digests / LAST_DIGEST
    if not p.exists():
        return None
    raw = p.read_text(encoding="utf-8").strip()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt


def build_new_stories(conn: sqlite3.Connection, now: datetime, cfg: dict) -> dict:
    digests = paths.digests_dir()
    last = read_last_digest(digests)
    if last is not None:
        start, basis = last, f"digests/{LAST_DIGEST}"
    else:
        start, basis = now - timedelta(hours=float(cfg["digest"]["fallback_hours"])), f"fallback: last {cfg['digest']['fallback_hours']}h"
    guard = start - timedelta(hours=BACKFILL_GUARD_HOURS)
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM clusters WHERE first_seen > ? AND last_published >= ?", (to_iso(start), to_iso(guard)))]
    clusters = queries.load_clusters(conn, ids)
    hits = queries.watch_hits(conn, ids, Matcher(load_watchlist()))
    stories = []
    for c in clusters:
        descs = list(dict.fromkeys(it["description"] for it in c["items"] if it["description"]))
        stories.append({
            "cluster_id": c["id"],
            "headline": c["headline"],
            "category": c["category"],
            "sources": [{"name": s["name"], "url": s["url"]} for s in c["sources"]],
            "outlet_count": c["outlet_count"],
            "watchlist_hits": hits.get(c["id"], []),
            "firms": c["firms"],
            "aum_usd": c["aum_usd"],
            "descriptions": descs,
            "first_seen": c["first_seen"],
            "published_at": c["last_published"],
        })
    # rank: watchlist hits, then outlet count, then recency
    stories.sort(key=lambda s: (-len(s["watchlist_hits"]), -s["outlet_count"], _neg_ts(s["published_at"])))
    tz = ZoneInfo(cfg["timezone"])
    return {
        "generated_at": to_iso(now),
        "local_date": now.astimezone(tz).date().isoformat(),
        "timezone": cfg["timezone"],
        "window_start": to_iso(start),
        "window_basis": basis,
        "count": len(stories),
        "stories": stories,
    }


def _neg_ts(iso: str) -> float:
    return -from_iso(iso).timestamp()


def write_new_stories(conn: sqlite3.Connection, now: datetime, cfg: dict) -> dict:
    data = build_new_stories(conn, now, cfg)
    path = paths.new_stories_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return data


# -- rendering ----------------------------------------------------------------------------------
ALLOWED_TAGS = ["a", "p", "br", "hr", "h1", "h2", "h3", "h4", "ul", "ol", "li", "strong", "em", "b", "i", "code",
                "pre", "blockquote", "table", "thead", "tbody", "tr", "th", "td"]
ALLOWED_ATTRS = {"a": ["href", "title"], "th": ["align"], "td": ["align"]}


def latest_digest(digests: Path | None = None) -> Path | None:
    digests = digests or paths.digests_dir()
    if not digests.exists():
        return None
    files = sorted((p for p in digests.iterdir() if _DIGEST_NAME.match(p.name)), key=lambda p: p.name)
    return files[-1] if files else None


def render_markdown(text: str) -> str:
    html = markdown.markdown(text, extensions=["extra", "sane_lists"])
    return bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, protocols=["http", "https", "mailto"], strip=True)


def digest_payload(top_n: int = 10) -> dict:
    path = latest_digest()
    if path is not None:
        return {"date": _DIGEST_NAME.match(path.name).group(1), "filename": f"digests/{path.name}",
                "html": render_markdown(path.read_text(encoding="utf-8"))}
    top, generated = [], None
    ns = paths.new_stories_path()
    if ns.exists():
        try:
            data = json.loads(ns.read_text(encoding="utf-8"))
            top, generated = data.get("stories", [])[:top_n], data.get("generated_at")
        except (ValueError, OSError):
            pass
    return {"date": None, "filename": None, "html": None, "top": top, "new_stories_generated_at": generated}
