"""Turn feed bytes into stored-item dicts. Only whitelisted fields are ever read."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import feedparser

from .dates import from_struct, parse_date, sane_published, to_iso
from .text import clean_description, clean_title, strip_source_suffix
from .urls import canonicalize


@dataclass
class Item:
    title: str
    url: str
    canonical_url: str
    source: str
    published_at: str
    published_estimated: bool
    fetched_at: str
    description: str


def looks_like_feed(parsed: feedparser.FeedParserDict) -> bool:
    version = parsed.get("version") or ""
    return bool(version) and (bool(parsed.entries) or version.startswith(("rss", "atom")))


def _summary(entry) -> str:
    """Description/summary element only. feedparser copies content:encoded into `summary` when an
    item has no <description>; detect that and discard it so full text never gets in."""
    summary = entry.get("summary") or ""
    if not summary:
        return ""
    for content in entry.get("content") or []:
        if (content.get("value") or "").strip() == summary.strip():
            return ""
    return summary


def parse_feed(
    content: bytes | str,
    source: str,
    fetched: datetime,
    gated: bool = False,
    local_tz: str = "America/Los_Angeles",
) -> tuple[list[Item], feedparser.FeedParserDict]:
    parsed = feedparser.parse(content)
    items: list[Item] = []
    fetched_iso = to_iso(fetched)
    for entry in parsed.entries:
        title = strip_source_suffix(clean_title(entry.get("title")), source)
        link = (entry.get("link") or "").strip()
        if not title or not link.startswith(("http://", "https://")):
            continue
        dt = from_struct(entry.get("published_parsed") or entry.get("updated_parsed"))
        if dt is None:
            dt = parse_date(entry.get("published") or entry.get("updated") or entry.get("dc_date"), local_tz)
        published, estimated = sane_published(dt, fetched)
        description = "" if gated else clean_description(_summary(entry))
        items.append(
            Item(
                title=title,
                url=link,
                canonical_url=canonicalize(link),
                source=source,
                published_at=to_iso(published),
                published_estimated=estimated,
                fetched_at=fetched_iso,
                description=description,
            )
        )
    return items, parsed
