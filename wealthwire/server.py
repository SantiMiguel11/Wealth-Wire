"""FastAPI app: JSON API + the static single-page UI. Re-ingests in the background."""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db, paths, queries
from .config import load_categories, load_config, load_sources
from .dates import to_iso
from .urls import clean_link
from .watchlist import Firm, Matcher, load_watchlist, save_watchlist

log = logging.getLogger("wealthwire.server")
PAGE_SIZE = 50
PIN_DAYS = 7
PIN_MAX = 10


async def _reingest_loop(interval_hours: float) -> None:
    from .ingest import run_ingest

    while True:
        await asyncio.sleep(interval_hours * 3600)
        try:
            log.info("background re-ingest starting")
            summary = await asyncio.to_thread(run_ingest, None, None, True)
            log.info("background re-ingest done: %s", summary)
        except Exception:  # keep the loop alive whatever happens
            log.exception("background re-ingest failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    if os.environ.get("WEALTHWIRE_NO_BACKGROUND") != "1":
        hours = float(load_config()["server"]["reingest_interval_hours"])
        task = asyncio.create_task(_reingest_loop(hours))
    yield
    if task:
        task.cancel()


app = FastAPI(title="Wealth Wire", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=paths.STATIC_DIR), name="static")


def _conn():
    return db.connect()


def _split(values: list[str] | None) -> list[str]:
    out: list[str] = []
    for v in values or []:
        out += [p.strip() for p in v.split(",") if p.strip()]
    return out


def _day_bound(value: str | None, field: str) -> str | None:
    """Accepts ISO datetimes (the UI sends local-day bounds converted to UTC) or YYYY-MM-DD (UTC day)."""
    if not value:
        return None
    try:
        if len(value) == 10:
            datetime.strptime(value, "%Y-%m-%d")
            return value + "T00:00:00Z"
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))

        return to_iso(dt)
    except ValueError:
        raise HTTPException(400, f"invalid {field}: {value!r}")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(paths.STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(paths.STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


@app.get("/api/feed")
def feed(
    q: str = "",
    source: list[str] | None = Query(None),
    category: list[str] | None = Query(None),
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    watch: bool = False,
    limit: int = Query(PAGE_SIZE, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    conn = _conn()
    try:
        ids = queries.matching_cluster_ids(
            conn, q=q, sources=_split(source), categories=_split(category),
            date_from=_day_bound(date_from, "from"), date_to=_day_bound(date_to, "to"),
        )
        matcher = Matcher(load_watchlist())
        hits = queries.watch_hits(conn, ids, matcher)
        pinned_ids: list[int] = []
        if watch:
            ids = [c for c in ids if hits[c]]
        else:
            # watchlist stories from the last week are pinned above the feed (and not repeated below)
            recent = {r[0] for r in conn.execute(
                "SELECT id FROM clusters WHERE last_published >= ?",
                (to_iso(queries.utcnow() - timedelta(days=PIN_DAYS)),))}
            pinned_ids = [c for c in ids if hits[c] and c in recent][:PIN_MAX]
            pinned_set = set(pinned_ids)
            ids = [c for c in ids if c not in pinned_set]
        page = queries.load_clusters(conn, ids[offset : offset + limit])
        pinned = queries.load_clusters(conn, pinned_ids) if offset == 0 else []
        for c in page + pinned:
            c["watchlist_hits"] = hits.get(c["id"], [])
        return {"pinned": pinned, "clusters": page, "total": len(ids), "offset": offset, "limit": limit}
    finally:
        conn.close()


@app.get("/api/trending")
def trending(days: int = Query(7, ge=1, le=90), limit: int = Query(15, ge=1, le=50)):
    conn = _conn()
    try:
        return queries.trending_firms(conn, days=days, limit=limit)
    finally:
        conn.close()


@app.get("/api/mna")
def mna(confidence: str | None = Query(None, pattern="^(high|low)?$")):
    conn = _conn()
    try:
        sql = "SELECT d.*, c.headline, c.url FROM mna_deals d JOIN clusters c ON c.id = d.cluster_id"
        params: list = []
        if confidence:
            sql += " WHERE d.confidence = ?"
            params.append(confidence)
        sql += " ORDER BY d.deal_date DESC, d.cluster_id DESC"
        rows = [dict(r) for r in conn.execute(sql, params)]
        for r in rows:
            seen, r["sources"] = set(), []
            for it in conn.execute("SELECT source, url FROM items WHERE cluster_id=? ORDER BY published_at, id", (r["cluster_id"],)):
                if it["source"] not in seen:
                    seen.add(it["source"])
                    r["sources"].append({"name": it["source"], "url": clean_link(it["url"])})
        return rows
    finally:
        conn.close()


class WatchIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    aliases: list[str] = Field(default_factory=list, max_length=20)


def _recompute_after_watchlist_change() -> None:
    """Firm extraction maps watchlist aliases to display names, so refresh derived data."""
    from .ingest import _LOCK
    from .pipeline import recompute

    with _LOCK:
        conn = _conn()
        try:
            recompute(conn, write_digest_input=False)
        finally:
            conn.close()


@app.get("/api/watchlist")
def get_watchlist():
    firms = load_watchlist()
    conn = _conn()
    try:
        since = to_iso(queries.utcnow() - timedelta(days=PIN_DAYS))
        ids = [r[0] for r in conn.execute("SELECT id FROM clusters WHERE last_published >= ?", (since,))]
        texts = queries.cluster_texts(conn, ids)
    finally:
        conn.close()
    out = []
    for f in firms:
        m = Matcher([f])
        out.append({"name": f.name, "aliases": f.aliases, "recent": sum(1 for t in texts.values() if m.hits(*t)),
                    "ignored_terms": [t for t in [f.name, *f.aliases] if len(t.replace(" ", "")) < 3]})
    return {"firms": out}


@app.post("/api/watchlist", status_code=201)
def add_watch(body: WatchIn):
    name = " ".join(body.name.split())
    aliases = [" ".join(a.split()) for a in body.aliases if a.strip()]
    if len(name.replace(" ", "")) < 3 and not any(len(a.replace(" ", "")) >= 3 for a in aliases):
        raise HTTPException(422, "Name must be at least 3 characters (shorter terms are never matched).")
    firms = load_watchlist()
    if any(f.name.lower() == name.lower() for f in firms):
        raise HTTPException(409, f"{name} is already on the watchlist.")
    firms.append(Firm(name, [a for a in dict.fromkeys(aliases) if a.lower() != name.lower()]))
    save_watchlist(firms)
    _recompute_after_watchlist_change()
    return {"ok": True, "name": name}


@app.delete("/api/watchlist/{name}")
def remove_watch(name: str):
    firms = load_watchlist()
    keep = [f for f in firms if f.name.lower() != name.strip().lower()]
    if len(keep) == len(firms):
        raise HTTPException(404, f"{name} is not on the watchlist.")
    save_watchlist(keep)
    _recompute_after_watchlist_change()
    return {"ok": True}


@app.get("/api/digest")
def digest():
    from .digest import digest_payload

    return digest_payload(int(load_config()["digest"]["top_n"]))


@app.get("/api/meta")
def meta():
    conn = _conn()
    try:
        status = {r["name"]: dict(r) for r in conn.execute("SELECT * FROM source_status")}
        sources = []
        for s in load_sources():
            st = status.get(s.name, {})
            sources.append({"name": s.name, "enabled": s.enabled, "gated": s.gated, "homepage": s.homepage,
                            "ok": bool(st.get("ok")), "method": st.get("method", "not run"),
                            "url_used": st.get("url_used", ""), "items_last_run": st.get("items_last_run", 0),
                            "new_last_run": st.get("new_last_run", 0), "reason": st.get("reason", ""),
                            "last_run_at": st.get("last_run_at", "")})
        lo, hi = queries.date_bounds(conn)
        return {
            "last_ingest": db.get_meta(conn, "last_ingest"),
            "demo": db.get_meta(conn, "demo") == "1",
            "items": conn.execute("SELECT COUNT(*) FROM items").fetchone()[0],
            "clusters": conn.execute("SELECT COUNT(*) FROM clusters").fetchone()[0],
            "categories": load_categories().categories,
            "sources": sources,
            "date_min": lo,
            "date_max": hi,
            "timezone": load_config()["timezone"],
        }
    finally:
        conn.close()


@app.exception_handler(Exception)
async def _unhandled(request, exc):  # JSON errors so the UI can show them
    log.exception("unhandled error")
    return JSONResponse({"detail": f"{type(exc).__name__}: {exc}"}, status_code=500)
