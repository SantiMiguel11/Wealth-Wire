"""Local preview server: builds the static site and serves it exactly as Vercel would.

    python -m wealthwire serve           # build from the current data dir, then serve http://localhost:8000

There is no API — the frontend reads /data/*.json like it does in production. /firm/<slug> falls back to
index.html (Vercel does the same with a rewrite). With WEALTHWIRE_NO_BACKGROUND unset, the server
re-ingests and rebuilds in the background every `server.reingest_interval_hours`.
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import paths
from .config import load_config

log = logging.getLogger("wealthwire.server")


def site_dir() -> Path:
    return paths.data_home() / "_site" / "site"


def rebuild() -> None:
    from .sitebuild import build_site

    build_site(paths.data_home() / "_site", write_state=False)


async def _refresh_loop(hours: float) -> None:
    from .ingest import run_ingest

    while True:
        await asyncio.sleep(hours * 3600)
        try:
            await asyncio.to_thread(run_ingest, None, None, True)
            await asyncio.to_thread(rebuild)
        except Exception:
            log.exception("background refresh failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    if os.environ.get("WEALTHWIRE_NO_BACKGROUND") != "1":
        task = asyncio.create_task(_refresh_loop(float(load_config()["server"]["reingest_interval_hours"])))
    yield
    if task:
        task.cancel()


def create_app(root: Path | None = None) -> FastAPI:
    root = root or site_dir()
    app = FastAPI(title="Wealth Wire (static preview)", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/firm/{slug}", include_in_schema=False)
    def firm_page(slug: str):
        return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})

    @app.middleware("http")
    async def noindex(request, call_next):
        resp: Response = await call_next(request)
        resp.headers["X-Robots-Tag"] = "noindex, nofollow"
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    app.mount("/", StaticFiles(directory=root, html=True), name="site")
    return app
