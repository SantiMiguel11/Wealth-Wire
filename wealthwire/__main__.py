"""CLI: python -m wealthwire {ingest,serve,recompute}"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _ensure_deps() -> None:
    """If this interpreter lacks the dependencies but the project venv exists, re-exec inside it.
    Lets `python -m wealthwire ingest` work from a scheduled task whatever `python` is on PATH."""
    try:
        import bleach, fastapi, feedparser, httpx, rapidfuzz, yaml  # noqa: F401
    except ImportError:
        venv_py = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        in_venv = Path(sys.prefix).resolve() == (ROOT / ".venv").resolve()
        if venv_py.exists() and not in_venv:
            os.chdir(ROOT)
            os.execv(str(venv_py), [str(venv_py), "-m", "wealthwire", *sys.argv[1:]])
        raise SystemExit("Missing dependencies. Run ./run.sh once (creates .venv) or: pip install -r requirements.txt")


def main(argv: list[str] | None = None) -> int:
    _ensure_deps()
    import argparse

    parser = argparse.ArgumentParser(prog="python -m wealthwire", description="Wealth Wire news aggregator")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_ing = sub.add_parser("ingest", help="fetch all sources once, recompute, write SOURCES.md and new_stories.json")
    p_ing.add_argument("--fixtures", type=Path, help="offline mode: serve requests from a fixture dir (routes.yaml)")
    p_srv = sub.add_parser("serve", help="start the web server (re-ingests in the background)")
    p_srv.add_argument("--host")
    p_srv.add_argument("--port", type=int)
    sub.add_parser("recompute", help="recompute categories/clusters/extraction from stored items")
    args = parser.parse_args(argv)

    if args.cmd == "ingest":
        from .ingest import run_ingest

        summary = run_ingest(fixtures=args.fixtures)
        return 0 if summary["sources_ok"] > 0 else 1
    if args.cmd == "recompute":
        from . import db
        from .pipeline import recompute

        conn = db.connect()
        print(recompute(conn))
        conn.commit()
        return 0
    if args.cmd == "serve":
        import uvicorn

        from .config import load_config

        cfg = load_config()["server"]
        uvicorn.run("wealthwire.server:app", host=args.host or cfg["host"], port=args.port or int(cfg["port"]), log_level="info")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
