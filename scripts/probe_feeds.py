"""Probe candidate feeds from where the refresh actually runs (GitHub Actions) and print what each returns.

For each directory page: every RSS link it offers (optionally filtered by --grep). For each feed: HTTP status,
item count, newest date, sample titles, and how many items the wealth filter (wires.keep_wire_item) would keep.
Uses the same Fetcher as ingestion (User-Agent with contact email, robots.txt, >=2s per host).

    python scripts/probe_feeds.py [--extra "URL URL ..."] [--grep "financ|invest|merger|wealth"]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wealthwire import db  # noqa: E402
from wealthwire.categorize import Categorizer  # noqa: E402
from wealthwire.config import load_categories, load_config  # noqa: E402
from wealthwire.dates import utcnow  # noqa: E402
from wealthwire.fetch import Fetcher  # noqa: E402
from wealthwire.firms import SecMatcher  # noqa: E402
from wealthwire.parse import parse_feed  # noqa: E402
from wealthwire.wires import WEALTH_TERMS, keep_wire_item  # noqa: E402

HREF = re.compile(r"""<a\b[^>]*href\s*=\s*["']([^"']+)["'][^>]*>(.*?)</a>""", re.I | re.S)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extra", default="", help="more feed URLs, space-separated")
    ap.add_argument("--grep", default=r"financ|invest|merger|acqui|wealth|asset|bank|advis",
                    help="only list directory links whose text or URL matches (case-insensitive)")
    ap.add_argument("--only-extra", action="store_true")
    args = ap.parse_args()
    cand = yaml.safe_load((ROOT / "scripts/probe_candidates.yaml").read_text())
    cfg = load_config()
    fetcher = Fetcher(cfg["user_agent"], per_host_delay=float(cfg["http"]["per_host_delay_seconds"]),
                      timeout=float(cfg["http"]["timeout_seconds"]), retries=1)
    conn = db.connect()
    sec = SecMatcher.from_db(conn)
    cat = Categorizer(load_categories())
    print(f"SEC advisers loaded for the filter: {len(sec.firms)}")
    grep = re.compile(args.grep, re.I)

    if not args.only_extra:
        for url in cand.get("directories", []):
            print(f"\n## DIRECTORY {url}")
            ok, why = fetcher.robots.check(url)
            if not ok:
                print(f"   robots: {why}")
                continue
            res = fetcher.get(url)
            if not res.ok:
                print(f"   {res.describe_failure()}")
                continue
            links = {}
            for href, text in HREF.findall(res.text):
                full = urljoin(res.url, href.strip())
                label = re.sub(r"<[^>]+>|\s+", " ", text).strip()
                if re.search(r"rss|feed|\.xml", full, re.I) and full not in links:
                    links[full] = label
            shown = {u: t for u, t in links.items() if grep.search(u) or grep.search(t)}
            print(f"   {len(links)} feed-like links; {len(shown)} match /{args.grep}/")
            for u, t in list(shown.items())[:80]:
                print(f"   - [{t[:60]}] {u}")

    feeds = ([] if args.only_extra else list(cand.get("feeds", []))) + args.extra.split()
    for url in feeds:
        print(f"\n## FEED {url}")
        ok, why = fetcher.robots.check(url)
        if not ok:
            print(f"   robots: {why}")
            continue
        res = fetcher.get(url)
        if not res.ok:
            print(f"   {res.describe_failure()}")
            continue
        items, parsed = parse_feed(res.content, "probe", utcnow())
        title = (parsed.feed.get("title") or "").strip()
        wealth = [i for i in items if WEALTH_TERMS.search(f"{i.title}\n{i.description}")]
        kept = [i for i in items if keep_wire_item(i.title, i.description, sec, cat)[0]]
        newest = max((i.published_at for i in items), default="—")
        print(f"   HTTP {res.status} · feed title {title!r} · {len(items)} items · newest {newest} · "
              f"wealth terms {len(wealth)} · kept by filter {len(kept)}")
        for i in items[:6]:
            print(f"   · {i.published_at[:10]} {i.title[:110]}")
        for i in kept[:10]:
            print(f"   ✓ kept: {i.title[:110]}")
    fetcher.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
