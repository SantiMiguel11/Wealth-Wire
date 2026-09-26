"""Google News RSS search feeds for outlets that block automated readers (§6).

We only read Google's public RSS search feed (e.g. q=site:thinkadvisor.com) — nothing is fetched from the
outlet itself, so the outlet's own bot blocking is respected, not circumvented.
- Items are attributed to the original outlet (the source name in sources.yaml), not to Google.
- Google appends " - <Outlet>" to every title; that suffix is stripped.
- Links are news.google.com redirect URLs. They are kept as-is (never resolved), so the usual canonical-URL
  dedupe can't work; the dedupe key is  gnews:<outlet>:<YYYY-MM-DD>:<normalized headline>.
- Google's <description> is an HTML list of links, not a publisher teaser, so descriptions are left empty.
"""
from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import quote, urlsplit

import feedparser

from .dates import from_struct, parse_date, sane_published, to_iso
from .parse import Item
from .text import clean_title

GNEWS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def feed_url(query: str) -> str:
    return GNEWS.format(q=quote(query, safe=":"))


def _host(url: str) -> str:
    h = (urlsplit(url or "").hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def dedupe_key(outlet: str, published_at: str, title: str) -> str:
    norm = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    return f"gnews:{outlet.lower()}:{published_at[:10]}:{norm}"


def strip_outlet_suffix(title: str, names: list[str]) -> str:
    for n in sorted({n for n in names if n}, key=len, reverse=True):
        stripped = re.sub(rf"\s+[-–—|]\s+{re.escape(n)}\s*$", "", title, flags=re.I)
        if stripped != title:
            return stripped.strip()
    return title


def parse_google_news(content: bytes | str, outlet: str, homepage: str, fetched: datetime,
                      local_tz: str = "America/Los_Angeles") -> tuple[list[Item], int]:
    """→ (items attributed to `outlet`, number of items skipped because Google attributed them elsewhere)."""
    parsed = feedparser.parse(content)
    want = _host(homepage)
    items, skipped, seen = [], 0, set()
    for e in parsed.entries:
        src = e.get("source") or {}
        src_name = (src.get("title") or "").strip()
        src_host = _host(src.get("href") or "")
        if want and src_host and not (src_host == want or src_host.endswith("." + want) or want.endswith("." + src_host)):
            skipped += 1  # the search returned another outlet's article
            continue
        title = strip_outlet_suffix(clean_title(e.get("title")), [src_name, outlet])
        link = (e.get("link") or "").strip()
        if not title or not link.startswith("https://"):
            continue
        dt = from_struct(e.get("published_parsed")) or parse_date(e.get("published"), local_tz)
        published, estimated = sane_published(dt, fetched)
        key = dedupe_key(outlet, to_iso(published), title)
        if key in seen:
            continue
        seen.add(key)
        items.append(Item(title=title, url=link, canonical_url=key, source=outlet, published_at=to_iso(published),
                          published_estimated=estimated, fetched_at=to_iso(fetched), description=""))
    return items, skipped
