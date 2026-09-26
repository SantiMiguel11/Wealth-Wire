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
    p = sub.add_parser("ingest", help="fetch all sources once, recompute, write SOURCES.md")
    p.add_argument("--fixtures", type=Path, help="offline mode: serve requests from a fixture dir (routes.yaml)")
    sub.add_parser("recompute", help="recompute categories/firms/clusters/M&A from stored items")
    p = sub.add_parser("build-site", help="write OUT/site (public) + OUT/state (private) + OUT/vercel.json")
    p.add_argument("out", type=Path)
    p.add_argument("--no-state", action="store_true", help="skip writing OUT/state")
    p = sub.add_parser("serve", help="build the static site and serve it locally (like Vercel)")
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    p.add_argument("--no-build", action="store_true", help="serve the last build as-is")
    p = sub.add_parser("state", help="carry data between refreshes through the live branch")
    p.add_argument("action", choices=["fetch", "restore"])
    p.add_argument("dir", type=Path, help="fetch: where to extract the previous live tree; restore: that tree")
    p.add_argument("--remote", default="origin")
    p.add_argument("--branch", default="live")
    p = sub.add_parser("publish", help="force-push OUT as a single orphan commit")
    p.add_argument("out", type=Path)
    p.add_argument("--remote-url", required=True)
    p.add_argument("--branch", default="live")
    p.add_argument("--message", default="Refresh")
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
    if args.cmd == "build-site":
        from .sitebuild import build_site

        print(build_site(args.out, write_state=not args.no_state))
        return 0
    if args.cmd == "serve":
        import uvicorn

        from .config import load_config
        from .server import create_app, rebuild

        if not args.no_build:
            rebuild()
        cfg = load_config()["server"]
        uvicorn.run(create_app(), host=args.host or cfg["host"], port=args.port or int(cfg["port"]), log_level="info")
        return 0
    if args.cmd == "state":
        from . import state

        if args.action == "fetch":
            ok = state.fetch_previous(args.dir, remote=args.remote, branch=args.branch)
            print(f"previous {args.branch}: {'extracted to ' + str(args.dir) if ok else 'none'}")
        else:
            print("restored:", state.restore(args.dir))
        return 0
    if args.cmd == "publish":
        from .state import publish

        publish(args.out, args.remote_url, args.branch, args.message)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
