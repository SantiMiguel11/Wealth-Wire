"""FastAPI app: JSON API + the static single-page UI. Re-ingests in the background."""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db, paths, queries
from .config import load_categories, load_config, load_sources

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
        from .dates import to_iso

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
    limit: int = Query(PAGE_SIZE, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    conn = _conn()
    try:
        ids = queries.matching_cluster_ids(
            conn, q=q, sources=_split(source), categories=_split(category),
            date_from=_day_bound(date_from, "from"), date_to=_day_bound(date_to, "to"),
        )
        page = queries.load_clusters(conn, ids[offset : offset + limit])
        return {"pinned": [], "clusters": page, "total": len(ids), "offset": offset, "limit": limit}
    finally:
        conn.close()


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
