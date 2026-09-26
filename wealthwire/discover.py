"""Feed autodiscovery and listing-page fallback (headline, link, date only)."""
from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from .dates import parse_date, sane_published, to_iso
from .parse import Item
from .text import clean_title
from .urls import canonicalize

FEED_TYPES = ("application/rss+xml", "application/atom+xml", "application/rdf+xml", "application/feed+json", "text/xml", "application/xml")
COMMON_PATHS = ("/feed", "/feed/", "/rss", "/rss.xml", "/feed.xml", "/atom.xml")


def find_alternate_feeds(html: str, base_url: str) -> list[str]:
    """<link rel="alternate" type="application/rss+xml" href="..."> in the page head."""
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []
    for link in soup.find_all("link", href=True):
        rel = link.get("rel") or []
        rel = [r.lower() for r in (rel if isinstance(rel, list) else [rel])]
        typ = (link.get("type") or "").lower().split(";")[0].strip()
        if "alternate" in rel and typ in FEED_TYPES:
            href = urljoin(base_url, link["href"])
            title = (link.get("title") or "").lower()
            # comment feeds are not news feeds
            if "comment" in title or "/comments/" in href:
                continue
            if href not in found:
                found.append(href)
    return found


def common_feed_urls(homepage: str) -> list[str]:
    parts = urlsplit(homepage)
    base = f"{parts.scheme}://{parts.netloc}"
    urls = [base + p for p in COMMON_PATHS]
    path = parts.path.rstrip("/")
    if path:  # section feeds, e.g. https://citywire.com/ria/feed
        urls = [base + path + p for p in ("/feed", "/rss")] + urls
    return urls


# -- listing-page fallback -------------------------------------------------------------------------
_ARTICLE_PATH = re.compile(r"(/\d{4}/\d{1,2}/|/news/|/article|/story/|/\d{5,}|-[a-z0-9]+-[a-z0-9]+-[a-z0-9]+)", re.I)
_SKIP_PATH = re.compile(r"/(tag|tags|category|categories|author|authors|topic|topics|page|search|login|subscribe|events?|podcasts?|videos?|webinars?)(/|$)", re.I)


def parse_listing(
    html: str,
    page_url: str,
    source: str,
    fetched: datetime,
    local_tz: str = "America/Los_Angeles",
    limit: int = 60,
) -> list[Item]:
    """Extract (headline, link, date) from a public listing page. Never reads article bodies."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
        tag.decompose()
    host = (urlsplit(page_url).hostname or "").lower()
    seen: set[str] = set()
    items: list[Item] = []
    candidates = soup.select("article a[href], h1 a[href], h2 a[href], h3 a[href], h4 a[href], a[href] h2, a[href] h3")
    for el in candidates:
        a = el if el.name == "a" else el.find_parent("a")
        if a is None:
            continue
        href = urljoin(page_url, a.get("href", ""))
        parts = urlsplit(href)
        if parts.scheme not in ("http", "https") or (parts.hostname or "").lower() != host:
            continue
        if _SKIP_PATH.search(parts.path) or not _ARTICLE_PATH.search(parts.path):
            continue
        title = clean_title(a.get_text(" "))
        if not (20 <= len(title) <= 220) or len(title.split()) < 4:
            continue
        canonical = canonicalize(href)
        if canonical in seen:
            continue
        seen.add(canonical)
        container = a.find_parent(["article", "li"]) or a.parent
        dt = None
        if container is not None:
            t = container.find("time")
            if t is not None:
                dt = parse_date(t.get("datetime") or t.get_text(" "), local_tz)
        published, estimated = sane_published(dt, fetched)
        items.append(
            Item(
                title=title,
                url=href,
                canonical_url=canonical,
                source=source,
                published_at=to_iso(published),
                published_estimated=estimated,
                fetched_at=to_iso(fetched),
                description="",
            )
        )
        if len(items) >= limit:
            break
    return items
